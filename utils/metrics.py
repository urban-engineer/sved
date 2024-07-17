import json
import math
import multiprocessing
import pathlib
import shutil

from utils import log
from utils import ffmpeg
from utils import ffprobe
from utils import mediainfo
from utils import requests_handler


# TODO: CAMBI evaluation
# https://github.com/Netflix/vmaf/blob/master/resource/doc/cambi.md

# duplicated from distributor/models.py, lazy, don't submit this.
def _format_bytes(file_size: int):
    if file_size and file_size > 0:
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(file_size, 1024)))
        s = round(file_size / math.pow(1024, i), 2)
        return "{}{}".format(s, size_name[i])
    else:
        return "0B"


def _download_vmaf_model(neg_mode: bool) -> pathlib.Path:
    if neg_mode:
        filename = "vmaf_v0.6.1neg.json"
    else:
        filename = "vmaf_v0.6.1.json"
    model_file = pathlib.Path.cwd().joinpath(filename)
    url = "https://raw.githubusercontent.com/Netflix/vmaf/master/model/{}".format(filename)

    if not model_file.exists():
        response = requests_handler.send_get_request(url)
        model_file.write_text(json.dumps(response.json(), indent=4))

    return model_file


def create_metrics_command(reference: pathlib.Path, compressed: pathlib.Path,
                           neg_mode: bool = False, subsample_rate: int = 1,
                           psnr: bool = True, ms_ssim: bool = True) -> str:
    if not reference.exists():
        raise ValueError("Path does not exist: [{}]".format(reference))
    if not compressed.exists():
        raise ValueError("Path does not exist: [{}]".format(compressed))

    # Downloading model file if it doesn't exist
    model_file = _download_vmaf_model(neg_mode)

    # Note about specifying framerate:
    #   I had a note-to-self about adding the framerate of each video as metrics_command for the ffmpeg command.
    #   On further research, this is only necessary if both videos have different framerates or variable framerates.
    #   What I encode does not have either of these issues, so this is not a concern.

    allowed_thread_count = math.floor(multiprocessing.cpu_count() * 0.9)
    command_template = "ffmpeg -progress - -nostats -hide_banner -y -stats_period 1 -loglevel warning"
    command_template += " -i \"{}\" -i \"{}\" -lavfi '{}libvmaf={}n_subsample={}"
    command_template += ":model=version={}|path={}:log_path=report.json:n_threads={}:log_fmt=json' -f null -"

    if psnr and not ms_ssim:
        feature_argument = "feature=name=psnr:"
    elif not psnr and ms_ssim:
        feature_argument = "feature=name=float_ms_ssim:"
    elif psnr and ms_ssim:
        feature_argument = "feature=name=psnr|name=float_ms_ssim:"
    else:
        feature_argument = ""

    # Adding the bwdif filter in the case where reference is interlaced and compressed isn't.
    # It would be a good idea to implement checks for when the reference isn't interlaced and the compressed is.
    # However, don't do that.
    reference_scan_type = mediainfo.get_media_info(reference).video_stream.get("ScanType", "")
    compressed_scan_type = mediainfo.get_media_info(compressed).video_stream.get("ScanType", "")
    if compressed_scan_type == "Progressive" and reference_scan_type != compressed_scan_type:
        interlace_filter = "[1:v]bwdif=0:-1:0[ref];[0:v][ref]"
    else:
        interlace_filter = ""

    metrics_command = command_template.format(
        compressed, reference, interlace_filter, feature_argument,
        subsample_rate, model_file.stem, model_file.name, allowed_thread_count
    )
    return metrics_command


def calculate_metrics(reference: pathlib.Path, compressed: pathlib.Path,
                      overwrite: bool = False, neg_mode: bool = False, subsample_rate: int = 1,
                      psnr: bool = True, ms_ssim: bool = True) -> pathlib.Path:
    metrics_command = create_metrics_command(
        reference, compressed,
        neg_mode=neg_mode, subsample_rate=subsample_rate,
        psnr=psnr, ms_ssim=ms_ssim
    )

    report_file = compressed.with_name(compressed.name.replace(".mkv", ".json"))
    if any([report_file.name == x.name for x in compressed.parent.iterdir()]):
        if overwrite:
            log.debug("Report file [{}] exists; overwriting".format(report_file))
        else:
            raise FileExistsError("Report file [{}] exists, will not overwrite".format(report_file))

    # Changing the output if both files have the same name
    if reference.name == compressed.name:
        reference_name = reference.relative_to(reference.parent.parent)
        compressed_name = compressed.relative_to(compressed.parent.parent)
    else:
        reference_name = reference.name
        compressed_name = compressed.name

    log.info("Calculating VMAF scores between [{}] and [{}]".format(reference_name, compressed_name))
    log.debug(metrics_command)

    file_info = ffprobe.get_file_info(reference)
    try:
        ffmpeg.handle_ffmpeg_return(file_info, metrics_command, print_output=True)
        shutil.move(pathlib.Path.cwd().joinpath("report.json"), report_file)
    except RuntimeError as rte:
        if str(rte).startswith("ffmpeg on"):
            code = str(rte).split("[")[2].split("]")[0]
            raise RuntimeError("vmaf on [{}] vs. [{}] returned code [{}]".format(reference.name, compressed.name, code))
        else:
            raise rte

    return report_file


def create_comparison_images(reference: pathlib.Path, compressed: pathlib.Path) -> pathlib.Path:
    images_folder = compressed.parent.joinpath(".".join(compressed.name.split(".")[:-1]))
    images_folder.mkdir(exist_ok=True, parents=True)

    vmaf_report_file = compressed.parent.joinpath(compressed.name.replace(".mkv", ".json"))
    if not vmaf_report_file.exists():
        raise FileNotFoundError(
            "Cannot create comparison images for [{}]: report does not exist".format(compressed.name)
        )

    log.debug("Reading VMAF report file for [{}]".format(compressed.name))
    vmaf_report = json.loads(vmaf_report_file.read_text())
    minimum_score = vmaf_report["pooled_metrics"]["vmaf"]["min"]
    low_frames = [x["frameNum"] for x in vmaf_report["frames"] if x["metrics"]["vmaf"] == minimum_score]

    log.debug("Found [{}] frames with lowest score; creating filter".format(len(low_frames)))
    select_filter = "select='"
    for frame_number in low_frames:
        select_filter += "eq(n\\,{})+".format(frame_number)
    select_filter = select_filter[:-1] + "'"

    windows_font_path_string = "fontfile=c\\:/Windows/Fonts/arial.ttf"

    reference_file_info = ffprobe.get_file_info(reference)
    if reference_file_info.video_stream["field_order"] == "progressive":
        deinterlace_argument = ""
    else:
        deinterlace_argument = ",bwdif=0"

    reference_arguments_template = "ffmpeg -progress - -nostats -hide_banner -y -stats_period 1 -loglevel"
    reference_arguments_template += " warning -i \"{}\" -y -vf \"setpts=N/TB, {}, crop=(in_w)/2:in_h:0:0,"
    reference_arguments_template += " drawtext='{}':fontsize=36:fontcolor='white':text='0':x=10:y=10{}\""
    reference_arguments_template += " -vsync 0 \"{}/0_%04d.png\""
    reference_images_arguments = reference_arguments_template.format(
        reference, select_filter, windows_font_path_string, deinterlace_argument, images_folder
    )

    log.debug("Extracting comparison frames from reference file")
    log.debug(reference_images_arguments)
    ffmpeg.handle_ffmpeg_return(reference_file_info, reference_images_arguments, print_output=False)

    compressed_file_info = ffprobe.get_file_info(compressed)
    compressed_arguments_template = "ffmpeg -progress - -nostats -hide_banner -y -stats_period 1 -loglevel"
    compressed_arguments_template += " warning -i \"{}\" -y -vf \"setpts=N/TB, {}, crop=(in_w)/2:in_h:(in_w)/2:0,"
    compressed_arguments_template += " drawtext='{}':fontsize=36:fontcolor='white':text='1':x=w-10-text_w/2:y=10\""
    compressed_arguments_template += " -vsync 0 \"{}/1_%04d.png\""
    compressed_images_arguments = compressed_arguments_template.format(
        compressed, select_filter, windows_font_path_string, images_folder
    )

    log.debug("Extracting comparison frames from compressed file")
    log.debug(compressed_images_arguments)
    ffmpeg.handle_ffmpeg_return(compressed_file_info, compressed_images_arguments, print_output=False)

    log.debug("Creating comparison images between reference and compressed files")
    for x in range(1, len(low_frames) + 1):
        command_template = "ffmpeg -progress - -nostats -hide_banner -y -stats_period 1 -y -i {} -i {}"
        command_template += " -filter_complex \"hstack=inputs=2\" \"{}/{}.png\""
        command = command_template.format(
            "\"{}/0_{}.png\"".format(images_folder, str(x).zfill(4)),
            "\"{}/1_{}.png\"".format(images_folder, str(x).zfill(4)),
            images_folder, str(low_frames[x - 1]).zfill(4)
        )

        ffmpeg.handle_ffmpeg_return(reference_file_info, command, print_output=False)
        images_folder.joinpath("0_{}.png".format(str(x).zfill(4))).unlink()
        images_folder.joinpath("1_{}.png".format(str(x).zfill(4))).unlink()

    return images_folder


# TODO: remove before public release, or make this better
def _get_lows(scores, low_type: str = "1%") -> float:
    if low_type == "1%":
        frame_count = len(scores) // 100
    elif low_type == "0.1%":
        frame_count = len(scores) // 1000
    else:
        raise ValueError("type should be \"1%\" or \"0.1%\"")

    return sum(sorted(scores)[0:frame_count]) / frame_count


def get_metrics_for_file(source_file_size: int, compressed_file: pathlib.Path, report_file: pathlib.Path):
    metrics = json.loads(report_file.read_text())

    vmaf = metrics["pooled_metrics"]["vmaf"]
    psnr = metrics["pooled_metrics"].get("psnr", metrics["pooled_metrics"].get("psnr_y"))
    ms_ssim = metrics["pooled_metrics"].get("ms_ssim", metrics["pooled_metrics"].get("float_ms_ssim"))

    vmaf_scores = []
    psnr_scores = []
    ssim_scores = []
    for frame in metrics["frames"]:
        vmaf_scores.append(frame["metrics"]["vmaf"])
        psnr_scores.append(frame["metrics"]["psnr_y"])
        ssim_scores.append(frame["metrics"]["float_ms_ssim"])

    psnr_one_percent = str(_get_lows(psnr_scores))
    ms_ssim_one_percent = str(_get_lows(ssim_scores))
    vmaf_one_percent = str(_get_lows(vmaf_scores))

    psnr_point_one_percent = str(_get_lows(psnr_scores, "0.1%"))
    ms_ssim_point_one_percent = str(_get_lows(ssim_scores, "0.1%"))
    vmaf_point_one_percent = str(_get_lows(vmaf_scores, "0.1%"))

    vmaf_string = "{}\t{}\t{}\t{}\t{}".format(
        str(vmaf["mean"]), str(vmaf["harmonic_mean"]),
        vmaf_one_percent, vmaf_point_one_percent, str(vmaf["min"])
    )

    if psnr:
        psnr_string = "{}\t{}\t{}\t{}\t{}".format(
            str(psnr["mean"]), str(psnr["harmonic_mean"]),
            psnr_one_percent, psnr_point_one_percent, str(psnr["min"])
        )
    else:
        psnr_string = "\t\t\t\t\t\t\t\t\t"

    if ms_ssim:
        ms_ssim_string = "{}\t{}\t{}\t{}\t{}".format(
            str(ms_ssim["mean"]), str(ms_ssim["harmonic_mean"]),
            ms_ssim_one_percent, ms_ssim_point_one_percent, str(ms_ssim["min"])
        )
    else:
        ms_ssim_string = "\t\t\t\t\t\t\t\t\t"

    compressed_file_size = compressed_file.stat().st_size
    file_info = ffprobe.get_file_info(compressed_file)
    bitrate = compressed_file_size / 1000.0 / file_info.duration * 8
    log.debug(
        "{}\t \t \t{}\t \t{}\t{}\t \t{}\t\t \t \t \t \t{}\t \t{}".format(
            compressed_file.name, compressed_file_size, bitrate,
            compressed_file_size / source_file_size, vmaf_string, psnr_string, ms_ssim_string
        )
    )


def print_metrics(reports_directory: pathlib.Path, source_file_size: int):
    for report_file in [x for x in reports_directory.iterdir() if x.is_file() and x.name.endswith(".json")]:
        compressed_video_file = report_file.with_suffix(".mkv")
        get_metrics_for_file(source_file_size, compressed_video_file, report_file)
