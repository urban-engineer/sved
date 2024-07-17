# General note: we assume any file passed into this module has already had statistics calculated by mkvtoolnix

# TODO: Support h265
# https://trac.ffmpeg.org/wiki/Encode/H.265
# -c:v libx265
# 2 pass: `-x265-params pass=1` & `-x265-params pass=2`
# need to use `-pix_fmt yuv420p10le` to encode to 10bit (even if source is 8bit or 12bit)
# pmode: `-x265-params pmode=1`
#
# ffmpeg -i base.mkv -map 0:v:0 -c:v:0 libx265 -preset X -crf X -profile:v main10
#        -pix_fmt yuv420p10le -x265-params high-tier=1:level=X high.mkv

# Putting all improvements here
#
# Optional Settings:
#   7.17.1) For complex video, --preset veryslow is encouraged.
#   7.17.2) --aq-mode 3 --aq-strength x.x
#           0.5-0.7 for grainy films.
#           0.6-0.9 for digital films.
#           0.9-1.1 for animation.
#   7.17.3) --psy-rd x.x:0.0
#           0.8-1.2 for films.
#           0.5-0.8 for animation.
#   7.17.4) --deblock x:x
#           -3:-3 for films.
#           1:1 for animation.
#
# Suggested command line:
#   7.26.2) x265 --high-tier --repeat-headers --aud --hrd --preset slow --level-idc X --crf X --range X --colorprim X
#                --transfer ## --colormatrix X --chromaloc X
#       7.26.2.1) If HDR append: --hdr10 --hdr10-opt --master-display ## --max-cll X
#       7.26.2.2) Optional tweaks: --no-cutree --no-open-gop --no-sao --pmode --aq-mode 4
#
# x265:
#   7.23.1) Range (--range), color primaries (--colorprim), transfer (--transfer), color matrix (--colormatrix) and
#   chroma sample location (--chromaloc) must be set to the same value as the source, or omitted if the source value is
#   undefined.

import json
import math
import os
import pathlib
import shlex
import subprocess
import typing

from utils import log
from utils import ffprobe
from utils import mkvtoolnix


BASE_FFMPEG_COMMAND = "ffmpeg -progress - -nostats -hide_banner -y -stats_period 1"


class FFmpegOutput:
    # frame=2931
    # fps=185.81
    # stream_0_0_q=23.0
    # bitrate=4078.7kbits/s
    # total_size=60817408
    # out_time_us=119287000
    # out_time_ms=119287000
    # out_time=00:01:59.287000
    # dup_frames=0
    # drop_frames=0
    # speed=7.56x
    # progress=continue
    def __init__(self, frame: int, fps: float, bitrate: float, total_size: int, out_time_us: int,
                 out_time_ms: int, out_time: str, dup_frames: int, drop_frames: int, speed: float,
                 file_framerate: float = None):
        self.frame: int = frame
        self.fps: float = fps
        self.bitrate: float = bitrate
        self.total_size: int = total_size
        self.out_time_us: int = out_time_us
        self.out_time_ms: int = out_time_ms
        self.out_time: str = out_time
        self.dup_frames: int = dup_frames
        self.drop_frames: int = drop_frames
        self.speed: float = speed

        if file_framerate and fps and speed == -1:
            self.speed = fps / file_framerate

    def detailed_string(self):
        return json.dumps(self.__dict__)

    def get_frame_as_percentage(self, frame_count: int):
        return self.frame / frame_count * 100.0

    def create_log_string(self, frame_count: int) -> str:
        formatted_frame_number = str(self.frame).zfill(len(str(frame_count)))
        remaining_frames = frame_count - self.frame
        if self.fps > 0:
            instant_eta = seconds_to_duration(remaining_frames / self.fps)
        else:
            instant_eta = "?"

        message_template = "{}/{} ({:6.2f}%) | fps: {:6.2f} | speed: {:5.2f}x | ETA: {:8s}"

        return message_template.format(
            formatted_frame_number,
            frame_count,
            self.get_frame_as_percentage(frame_count),
            self.fps,
            self.speed,
            instant_eta
        )

    def __str__(self):
        return "frame: {} | fps: {} | speed: {}".format(self.frame, self.fps, self.speed)

    def __repr__(self):
        return "frame: {} | fps: {} | speed: {} | bitrate: {}".format(self.frame, self.fps, self.speed, self.bitrate)


def format_ffmpeg_output(ffmpeg_output: typing.List[str], file_framerate: float = None) -> FFmpegOutput:
    """
    Takes ffmpeg progress output and returns an object to be better interact with it.

    Needed since the way I print ffmpeg output it's one metric per line, not one progress step per line.

    :param ffmpeg_output: list of lines from ffmpeg encoding output
    :param file_framerate: optional parameter, provide this to calculate speed if ffmpeg returning 'N/A'
    :return: output object that's easier to manipulate
    """
    # Ignoring output like "stream_0_1_q=0.0"
    temp_stdout = [x for x in ffmpeg_output if "stream_" not in x]

    if "bitrate=N/A" in temp_stdout[2]:
        temp_stdout[2] = "bitrate=-1"
    if "total_size=N/A" in temp_stdout[3]:
        temp_stdout[3] = "total_size=-1"
    if "out_time_us=N/A" in temp_stdout[4]:
        temp_stdout[4] = "out_time_us=-1"
    if "out_time_ms=N/A" in temp_stdout[5]:
        temp_stdout[5] = "out_time_ms=-1"
    if "out_time=N/A" in temp_stdout[6]:
        temp_stdout[6] = "out_time=-1"
    if "speed=N/A" in temp_stdout[9]:
        temp_stdout[9] = "speed=-1x"

    try:
        return FFmpegOutput(
            frame=int(temp_stdout[0].split("=")[1]),
            fps=float(temp_stdout[1].split("=")[1]),
            bitrate=float(temp_stdout[2].split("=")[1].split("kbits")[0]),
            total_size=int(temp_stdout[3].split("=")[1]),
            out_time_us=int(temp_stdout[4].split("=")[1]),
            out_time_ms=int(temp_stdout[5].split("=")[1]),
            out_time=temp_stdout[6].split("=")[1],
            dup_frames=int(temp_stdout[7].split("=")[1]),
            drop_frames=int(temp_stdout[8].split("=")[1]),
            speed=float(temp_stdout[9].split("=")[1].split("x")[0]),
            file_framerate=file_framerate
        )
    except ValueError as ve:
        log.debug(ffmpeg_output)
        log.debug(temp_stdout)
        raise ve


def _construct_audio_stream_arguments(audio_streams: typing.List[dict]) -> str:
    # It's never really worth it to keep the original audio because it's so massive.
    # (Audiophiles: I do not care.  You and I are both well aware neither your nor my hearing can tell a difference.)

    # Automatic audio encoding rules:
    # General: AAC, 96kb/s per channel
    # Main audio track:
    #   If greater than 5.1, downmix to 5.1, encode to 576kb/s
    #   If 5.1 and greater than 576kb/s, encode to 576kb/s
    #   If stereo or mono and greater than 192kb/s, encode to 192kb/s
    #   If greater than stereo, also encode a stereo 192kb/s with a +2 db gain track for compatibility
    # Secondary audio tracks:
    #   If greater than stereo, encode to stereo 192kb/s with a +2 db gain
    #   If stereo or mono and greater than 192kb/s, encode to 192kb/s

    # I'm aware that general logic says the FDK AAC encoder is better than ffmpeg's built-in encoder.
    # However, I do not care to compile my own binaries (which would mean I can't distribute this project easily),
    # nor have I noticed any issues while listening to AAC tracks encoded with ffmpeg's built-in encoder.
    # I'm sure that if I was getting down to 128kb/s, and I was listening on a fine-tuned 5.1 surround system,
    # that I would notice _some_ difference.  But I watch my shows and movies on budget gear and have a
    # basic 2 channel soundbar for my TV.  96kb/s per channel encoded to AAC sounds fine to me.

    # I'm also aware that Opus is superior to AAC at these bitrates.  But considering that Opus cannot be
    # direct played via Plex very often, I'd rather just go with AAC and save the headache.
    # If I'm going to be preparing videos for easy playback, I might as well prep the audio too.

    # These templates make things a bit easier.  They all have the same base,
    # encoding to AAC with a bitrate of 96 kb/s per channel.  So we just fill those in automatically ahead of time.

    #                copy without modifying
    copy_template = "-map 0:a:{} -c:a:{} copy"

    # Makes it easier to change (or configure) in the future if I decide to get wacky with bitrates.
    bitrate_per_channel = 96

    # I've left a quick note above each argument for what it does, but here's more context for future debugging:
    # "-map 0:a:{}"                 : Select this stream from the source file, the {} is filled in later.
    # "-c:a:{} aac"                 : Encode stream to AAC
    # "-b:a:{} {}k"                 : Encode stream to bitrate.  Without the ":{}", it applies to _all_ streams
    # "-filter:a:{} \"volume=2dB\"" : Adds a 2dB gain to the track, used for surround -> stereo downmixes.
    # "-ac:a:{} {}"                 : Number of audio channels.  Without the ":{}", it applies to _all_ streams

    #                        re-encode   to aac      bitrate    gain  channels
    base_encode_template = "-map 0:a:{} -c:a:{} aac -b:a:{} {}k {}   -ac:a:{} {}"

    # Actual templates to be used.  We have to add "{}" since those need to be filled in for each output stream later.

    # Final template: "-map 0:a:{} -c:a:{} aac -b:a:{} 576k    -ac:a:{} 6"
    # Example result: "-map 0:a:0  -c:a:0  aac -b:a:0  576k    -ac:a:0  6"
    five_point_one_template = base_encode_template.format(
        "{}", "{}", "{}", bitrate_per_channel * 6, "", "{}", 6
    )

    # Final template: "-map 0:a:{} -c:a:{} aac -b:a:{} 192k -filter:a:{} \"volume=2dB\"   -ac:a:{} 2"
    # Example result: "-map 0:a:0  -c:a:1  aac -b:a:1  192k -filter:a:1  \"volume=2dB\"   -ac:a:1  2"
    stereo_gain_template = base_encode_template.format(
        "{}", "{}", "{}", bitrate_per_channel * 2, "-filter:a:{} \"volume=2dB\"", "{}", 2
    )

    # Final template: "-map 0:a:{} -c:a:{} aac -b:a:{} 192k    -ac:a:{} 2"
    # Example result: "-map 0:a:1  -c:a:2  aac -b:a:2  192k    -ac:a:2 2"
    stereo_no_gain_template = base_encode_template.format(
        "{}", "{}", "{}", bitrate_per_channel * 2, "", "{}", 2
    )

    audio_arguments = []

    # Since the flags for main audio are different from generalized "secondary" audio, we have to pull
    # them out of the loop.  But it's functionally the same as below, just pointed at the first audio track.
    main_track_bitrate = int(audio_streams[0]["tags"]["BPS"]) // 1000
    main_track_channels = int(audio_streams[0]["channels"])
    main_track_codec = audio_streams[0]["codec_name"]

    if main_track_channels >= 6:
        if main_track_bitrate > 576:
            audio_arguments.append(five_point_one_template.format(0, 0, 0, 0))
        else:
            audio_arguments.append(stereo_gain_template.format(0, 0, 0, 0, 0))
    else:
        if main_track_bitrate > 192:
            audio_arguments.append(stereo_no_gain_template.format(0, 0, 0, 0))
        else:
            if main_track_codec == "aac":
                audio_arguments.append(copy_template.format(0, 0))
            else:
                audio_arguments.append(stereo_no_gain_template.format(0, 0, 0, 0))

    # Compatibility track creation.  This includes the +2db gain for downmixing to stereo for 5.1 (or more) tracks.
    if main_track_channels > 2:
        audio_arguments.append(
            stereo_gain_template.format(
                0, len(audio_arguments), len(audio_arguments), len(audio_arguments), len(audio_arguments)
            )
        )

    # Any additional tracks.
    # I'm aware that the base logic is the nearly identical to the main audio track (without the concern for 5.1 or 7.1)
    # However I find it easier to debug when they're separated,
    # and I would do anything to make future me not want to kill current me.
    for i in range(1, len(audio_streams)):
        track_bitrate = int(audio_streams[i]["tags"]["BPS"]) // 1000
        track_channels = int(audio_streams[i]["channels"])
        track_codec = audio_streams[i]["codec_name"]

        if track_channels >= 6:
            audio_arguments.append(
                stereo_gain_template.format(
                    i, len(audio_arguments), len(audio_arguments), len(audio_arguments), len(audio_arguments)
                )
            )
        elif track_bitrate >= 192:
            audio_arguments.append(
                stereo_no_gain_template.format(i, len(audio_arguments), len(audio_arguments), len(audio_arguments))
            )
        else:
            if track_codec == "aac":
                audio_arguments.append(copy_template.format(i, len(audio_arguments)))
            else:
                audio_arguments.append(
                    stereo_no_gain_template.format(i, len(audio_arguments), len(audio_arguments), len(audio_arguments))
                )

    # We join-split-join to remove any duplicate whitespace
    return " ".join(" ".join(audio_arguments).split())


def _construct_video_filter_arguments(file: pathlib.Path) -> str:
    """
    Creates necessary video filter arguments for producing SCENE-compliant video.
    Specifically, adds filters to de-interlace.

    Do note that the de-interlacing filter is only applied if the source media is flagged as interlaced.
    So there is a non-zero chance it may fail to be used on video with malformed metadata.

    If no filters are necessary, this returns an empty string.

    This function originally checked if a video could be cropped as well, because that saves bitrate and is
    allowed by the SCENE rules.  However, you cannot calculate PSNR/MS-SSIM/VMAF scores on videos that are not
    the same height & width.  Thus, I have removed the crop detection.  I have left the function a bit over-engineered
    in case I want to add other video filters.  I am not opposed to reducing this down to just deinterlace detection.

    :param file: file to run cropdetect filter on
    :return: string of arguments necessary to de-interlace and remove black bars from video
    """
    file_info = ffprobe.get_file_info(file)

    if file_info.video_stream["field_order"] == "progressive":
        deinterlace_arguments = ""
    else:
        # Use the bwdif filter, one frame output per frame input.
        deinterlace_arguments = "bwdif=0"

    if deinterlace_arguments:
        filter_arguments = "-vf {}".format(deinterlace_arguments)
    else:
        filter_arguments = ""

    return filter_arguments


def _construct_video_stream_arguments(file: pathlib.Path, codec: str,
                                      encode_type: str, encode_value: int,
                                      preset: str, tune: str = None) -> str:
    if codec not in ["libx264", "libx265"]:
        raise ValueError("Codec [{}] not supported".format(codec))

    command_fragment = "-map 0:v:0 -c:v:0 {} -preset {}".format(codec, preset)
    x265_parameters = []

    if tune and tune in ["film", "grain", "animation"]:
        command_fragment += " -tune {}".format(tune)

    if encode_type == "crf":
        command_fragment += " -crf {}".format(encode_value)
    elif encode_type == "abr1":
        if codec == "libx264":
            command_fragment += " -b:v {}k -pass 1 -passlogfile \"{}\"".format(encode_value, file.stem)
        else:
            command_fragment += " -b:v {}k".format(encode_value)
            x265_parameters.append("pass=1")
            x265_parameters.append("stats={}.log".format(file.stem))
    elif encode_type == "abr2":
        if codec == "libx264":
            command_fragment += " -b:v {}k -pass 2 -passlogfile \"{}\"".format(encode_value, file.stem)
        else:
            command_fragment += " -b:v {}k".format(encode_value)
            x265_parameters.append("pass=2")
            x265_parameters.append("stats={}.log".format(file.stem))
    else:
        raise ValueError("Encode type [{}] not supported".format(encode_type))

    level = _get_scene_level(file)

    if codec == "libx264":
        command_fragment += " -level:v {}".format(level)
    else:
        # 10 bit
        command_fragment += " -pix_fmt yuv420p10le"

        # Level 4.2 does not exist for h265, h265's 4.1 covers h264's 4.2 completely.
        if level == "4.2":
            level = "4.1"

        # Additional arguments only provided via -x265-params, put at the end for clarity
        x265_parameters.append("high-tier=1")
        x265_parameters.append("level={}".format(level))
        command_fragment += " -x265-params {}".format(":".join(x265_parameters))

    return command_fragment


def _get_scene_level(file: pathlib.Path) -> str:
    """
    Get the appropriate level for video encoding as defined by SCENE rules.

    * 720p - '4.1'
    * 1080p - '4.2' above 30 fps, '4.1' otherwise
    * 2160p - '5.2' above 30 fps, '5.1' otherwise

    :param file: video file to check
    :return: string representing the appropriate encode level, e.g. "4.1"
    """

    file_info = ffprobe.get_file_info(file)
    height = int(file_info.video_stream["height"])

    # I am aware of the dangers of using `eval()`.
    # However, only data curated by the user should reach this stage which means it's not a concern.
    # If someone manages to Do Nefarious Deeds because of this, I'll be honestly impressed.
    frame_rate = float(eval(file_info.video_stream["r_frame_rate"]))

    if height > 1080:
        if frame_rate > 30:
            return "5.2"
        else:
            return "5.1"
    elif height > 720 and frame_rate > 30:
        return "4.2"
    else:
        return "4.1"


def seconds_to_duration(seconds: float) -> str:
    """
    Convert a float of seconds to a string formatted duration, hh:mm:ss (rounded)

    :param seconds:
    :return:
    """
    if seconds >= 0:
        hours = int(seconds // 3600)
        seconds = seconds % 3600
        minutes = int(seconds % 3600 // 60)
        seconds = round(seconds % 60)
        return "{:02}:{:02}:{:02}".format(hours, minutes, seconds)
    else:
        return ""


def get_max_video_stream_size_for_scene(file: pathlib.Path) -> int:
    """
    Get the maximum file size based off scene rules.  See: https://scenerules.org/t.html?id=2020_X265.nfo 7.6

    :param file: video file to check
    :return: maximum size (in bytes) as specified by scene rules
    """
    file_info = ffprobe.get_file_info(file)

    # Height rules
    # Since not everything is perfectly 720p/1080p/2160p, scene rules 4.1 - 4.3 are used here to determine the
    # 'category' of height (categories being the previously listed resolutions).
    hd_resolution = (1280, 720)
    full_hd_resolution = (1920, 1080)
    ultra_hd_resolution = (3840, 2160)

    video_width = file_info.video_stream["width"]
    video_height = file_info.video_stream["height"]
    aspect_ratio = round(video_width / video_height, 2)

    if aspect_ratio >= 1.78:
        if video_width <= hd_resolution[0]:
            category = "720p"
        elif video_width == full_hd_resolution[0]:
            category = "1080p"
        elif video_width == ultra_hd_resolution[0]:
            category = "2160p"
        else:
            raise ValueError("File [{}] has unexpected width [{}]".format(file.name, video_width))
    else:
        if video_height <= hd_resolution[1]:
            category = "720p"
        elif video_height == full_hd_resolution[1]:
            category = "1080p"
        elif video_height == ultra_hd_resolution[1]:
            category = "2160p"
        else:
            raise ValueError("File [{}] has unexpected height [{}]".format(file.name, video_height))

    # Now we use rule 7.6 to get max output size of the stream.  30%/60%/70% for 720p/1080p/2160p respectively
    video_stream_size = float(file_info.video_stream["tags"]["NUMBER_OF_BYTES"])
    if category == "720p":
        return math.floor(video_stream_size * 0.3)
    elif category == "1080p":
        return math.floor(video_stream_size * 0.6)
    else:
        return math.floor(video_stream_size * 0.7)


def get_bitrate_for_scene(file_path: pathlib.Path) -> int:
    """
    Given an input file, get the max allowed bitrate (in Kb/s) of the file allowed by scene rules

    :param file_path: path to source file to check
    :return: max average bitrate for input file
    """
    file_info = ffprobe.get_file_info(file_path)
    scene_max_kilobits = get_max_video_stream_size_for_scene(file_path) / 1000 * 8
    return math.floor(scene_max_kilobits / file_info.duration)


def passes_scene_rules(reference_file: pathlib.Path, compressed_file: pathlib.Path) -> bool:
    """
    Check if a compressed file's video stream is equal or below scene rule maximum.

    :param reference_file: path to uncompressed file
    :param compressed_file: path to compressed file
    :return: whether the compressed file passes scene rules or not
    """
    compressed_information = ffprobe.get_file_info(compressed_file)
    max_video_stream_size = get_max_video_stream_size_for_scene(reference_file)
    return float(compressed_information.video_stream["tags"]["NUMBER_OF_BYTES"]) <= max_video_stream_size


def delete_two_pass_logs(log_directory: pathlib.Path) -> None:
    """
    Deleting files left behind by a two pass encode

    :param log_directory: directory containing two pass log (likely the current working directory)
    :return: None
    """
    log_prefix = "ffmpeg2pass-0"
    for file in log_directory.iterdir():
        if file.name.startswith(log_prefix):
            file.unlink()


def create_two_pass_command_by_relative_size(file_path: pathlib.Path, output_path: pathlib.Path = None,
                                             codec: str = "h264", stream_size: float = None,
                                             preset: str = "slow",
                                             tune: str = None) -> typing.Tuple[str, str, pathlib.Path]:
    """
    Simple wrapper to get 2-pass commands to encode down to a percentage video stream size rather than
    calculating and providing the bitrate.

    :param file_path: path to source file to encode
    :param output_path: path to encoded file
    :param codec: video codec to use (h264 or h265)
    :param stream_size: size of encoded video stream relative to source video stream
    :param preset: encoder preset (e.g. slow, medium, veryfast)
    :param tune: encoder tune
    :return: Commands necessary to encode a video with two-pass encoding and the path to the output file if run.
    """
    if stream_size:
        file_info = ffprobe.get_file_info(file_path)
        video_stream_size = float(file_info.video_stream["tags"]["NUMBER_OF_BYTES"])
        compressed_stream_size = int(math.floor(video_stream_size * stream_size) / 1000 * 8)
        bitrate = math.floor(compressed_stream_size / file_info.duration)
    else:
        bitrate = get_bitrate_for_scene(file_path)
    return create_two_pass_command(file_path, output_path, codec, bitrate=bitrate, preset=preset, tune=tune)


def create_two_pass_command(file_path: pathlib.Path, output_path: pathlib.Path = None,
                            codec: str = "h264", bitrate: int = None,
                            preset: str = "slow", tune: str = None) -> typing.Tuple[str, str, pathlib.Path]:
    """
    Create commands to encode a file with ffmpeg using two-pass encoding.

    These parameters are optional and will be filled in during function execution if not provided:

    * `output_path` will be a file name "abr_2pass_<source filename.ext>" next to the source file.
    * `bitrate` will be set to the SCENE-acceptable bitrate (30%/60%/70% for 720p/1080p/2160p respectively)

    :param file_path: path to source file to encode
    :param output_path: path to encoded file
    :param codec: video codec to use (h264 or h265)
    :param bitrate: average bitrate in kilobits per second
    :param preset: encoder preset (e.g. slow, medium, veryfast)
    :param tune: encoder tune
    :return: Commands necessary to encode a video with two-pass encoding and the path to the output file if run.
    """
    mkvtoolnix.add_media_statistics_if_necessary(file_path)
    file_info = ffprobe.get_file_info(file_path)

    if not output_path:
        output_path = file_path.parent.joinpath("output", "abr_2pass_{}".format(file_path.name))
    output_path.parent.mkdir(exist_ok=True, parents=True)

    if not bitrate:
        bitrate = get_bitrate_for_scene(file_path)

    if codec == "h264":
        video_codec = "libx264"
    elif codec == "h265":
        video_codec = "libx265"
    else:
        raise ValueError("Got codec value [{}]; expected one of (h264,h265)".format(codec))

    # Handling first pass output, Windows and Linux don't output to nothing the same way.
    if os.name == "nt":
        two_pass_output = "NUL"
    else:
        two_pass_output = "/dev/null"

    first_pass_video_stream_arguments = _construct_video_stream_arguments(
        file_path, video_codec, "abr1", bitrate, preset, tune
    )

    first_pass_command_template = "{} -i \"{}\" {} -f null {}"
    first_pass_command = first_pass_command_template.format(
        BASE_FFMPEG_COMMAND, file_path, first_pass_video_stream_arguments, two_pass_output
    )

    second_pass_command_template = "{} -i \"{}\" -movflags use_metadata_tags"

    # Video arguments, encoding settings then filters
    second_pass_command_template += " {} {}"

    # Audio & subtitle arguments, output path
    second_pass_command_template += " {} {} \"{}\""

    second_pass_video_stream_arguments = _construct_video_stream_arguments(
        file_path, video_codec, "abr2", bitrate, preset, tune
    )
    filter_arguments = _construct_video_filter_arguments(file_path)

    if file_info.subtitle_streams:
        subtitle_arguments = "-map 0:s -c:s copy"
    else:
        subtitle_arguments = ""

    if file_info.audio_streams:
        audio_arguments = _construct_audio_stream_arguments(file_info.audio_streams)
    else:
        audio_arguments = ""

    second_pass_command = second_pass_command_template.format(
        BASE_FFMPEG_COMMAND, file_path,
        second_pass_video_stream_arguments, filter_arguments,
        subtitle_arguments, audio_arguments, output_path
    )

    return " ".join(first_pass_command.split()), " ".join(second_pass_command.split()), output_path


def create_crf_command(file_path: pathlib.Path, output_path: pathlib.Path = None,
                       codec: str = "h264", crf: int = 18, preset: str = "slow",
                       tune: str = None) -> typing.Tuple[str, pathlib.Path]:
    """
    Create commands to encode a file with ffmpeg using two-pass encoding.

    These parameters are optional and will be filled in during function execution if not provided:

    * `output_path` will be a file name "crf_<source filename.ext>" next to the source file.
    * `crf` will be set to 18 (SCENE recommends 17/17/16/14 720p/1080p/2160p/"especially compressible 2160p")

    :param file_path: path to source file to encode
    :param output_path: path to encoded file
    :param codec: video codec to use (h264 or h265)
    :param crf: CRF to encode with
    :param preset: encoder preset (e.g. slow, medium, veryfast)
    :param tune: encoder tune
    :return: Commands necessary to encode a video with two-pass encoding and the path to the output file if run.
    """
    mkvtoolnix.add_media_statistics_if_necessary(file_path)
    file_info = ffprobe.get_file_info(file_path)

    if not output_path:
        output_path = file_path.parent.joinpath("output", "crf_{}".format(file_path.name))
        output_path.parent.mkdir(exist_ok=True, parents=True)

    if codec == "h264":
        video_codec = "libx264"
    elif codec == "h265":
        video_codec = "libx265"
    else:
        raise ValueError("Got codec value [{}]; expected one of (h264,h265)".format(codec))

    # TODO: ignore any thumbnail streams
    command_template = "{} -i \"{}\" -movflags use_metadata_tags"

    # Video arguments, encoding settings then filters
    command_template += " {} {}"

    # Audio & subtitle arguments, output path
    command_template += " {} {} \"{}\""

    # Getting values from here to end
    video_stream_arguments = _construct_video_stream_arguments(file_path, video_codec, "crf", crf, preset, tune)
    video_filter_arguments = _construct_video_filter_arguments(file_path)

    if file_info.subtitle_streams:
        subtitle_arguments = "-map 0:s -c:s copy"
    else:
        subtitle_arguments = ""

    if file_info.audio_streams:
        audio_arguments = _construct_audio_stream_arguments(file_info.audio_streams)
    else:
        audio_arguments = ""

    command = command_template.format(
        BASE_FFMPEG_COMMAND, file_path,
        video_stream_arguments, video_filter_arguments,
        subtitle_arguments, audio_arguments, output_path
    )

    return " ".join(command.split()), output_path


def change_container(input_file: pathlib.Path, container: str = "mkv") -> pathlib.Path:
    """
    Remuxes video file to a different container.

    Note there is no error checking here, e.g. trying to remux to mp4 with unsupported stream codecs.

    :param input_file: File to remux
    :param container: file extension to remux to (default `mkv`)
    :return: path to remuxed file
    """
    if input_file.name.lower().endswith(container):
        return input_file
    file_info = ffprobe.get_file_info(input_file)

    output_file = input_file.with_name("{}.{}".format(input_file.stem, container))

    command = "{} -i \"{}\"  -vcodec copy -acodec copy \"{}\"".format(
        BASE_FFMPEG_COMMAND, input_file, output_file
    )
    log.debug("Converting [{}] to [{}]".format(input_file.name, output_file.name))
    handle_ffmpeg_return(file_info=file_info, command=command, print_output=False)
    mkvtoolnix.add_media_statistics(output_file)
    return output_file


def handle_ffmpeg_return(file_info: ffprobe.FFProbeFile, command: str,
                         print_output=False) -> (int, typing.List[str], typing.List[FFmpegOutput]):
    """
    Just handle ffmpeg commands generically - run it, if it fails, print stdout if there is and then throw an exception

    :param file_info: input file info
    :param command: ffmpeg command to run
    :param print_output: whether to print output live or not
    :return: return code, stdout, list of FFmpegOutput steps (stdout but formatted)
    """
    code, out, steps = run_ffmpeg_command(
        command, file_info.frames,
        file_framerate=float(eval(file_info.video_stream["r_frame_rate"])), print_output=print_output
    )
    if code != 0:
        if out and not print_output:
            log.debug(out)
        raise RuntimeError("ffmpeg on [{}] returned code [{}]".format(file_info.path.name, code))


def run_ffmpeg_command(command: str, frame_count: int, file_framerate: float = None,
                       print_output=False) -> (int, typing.List[str], typing.List[FFmpegOutput]):

    # TODO: figure out a way to print a cool progress bar if in an active terminal.

    stdout = []
    temp_stdout = []
    output_steps = []
    in_progress = False  # Used so we can ignore output before we start encoding
    hit_end = False

    process = subprocess.Popen(
        shlex.split(command),
        universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="backslashreplace"
    )

    while True:
        process_stdout = process.stdout.readline().strip()
        if process_stdout == "" and process.poll() is not None:
            break

        stdout.append(process_stdout)
        if process_stdout and not hit_end:
            if not in_progress and "frame=" in process_stdout:
                in_progress = True

            if in_progress and "=" in process_stdout and process_stdout.count("=") == 1:
                if process_stdout.startswith("["):
                    # This is to filter output like:
                    #  `[null @ 0000029040a27780] Application provided invalid, <trunc> 0: 369 >= 369`
                    # However sometimes that gets managed with what we're looking for, e.g.:
                    #  `[null @ 0000029040a27780] frame=380`
                    # I'm going to assume that this can't happen twice in a row, e.g.:
                    #  `[null @ 0000029040a27780] frame=380`
                    #  `[null @ 0000029040a27780] fps=74.63`
                    # And check if "frame=" is present, and if so, extract it and process as normal
                    if "frame=" in process_stdout:
                        temp_stdout.append(process_stdout.strip().split("] ")[1])
                    continue

                # This is a corollary check to the check above.  In the event that ffmpeg sends an update to stdout
                # while it's sending another message, you may get output like:
                #  `[null @ 0000013894ef1f00] Application provided invalid, <trunc> 0: 1641 >= 1641`
                #  `[null @ 0000013894ef1f00] frame=1646
                #  `fps=67.94`
                #  `<further progress output truncated>`
                #  `Application provided invalid, <trunc> 0: 1645 >= 1645`
                # The first message being sent gets interrupted by a progress update, then resumes being printed
                # So this check is to handle that.
                # I imagine there's a better solution here, but handling this edge case is easier for the moment.
                if " " in process_stdout.strip().split("=")[0]:
                    continue

                temp_stdout.append(process_stdout.strip())

                if "progress=" in process_stdout:
                    output = format_ffmpeg_output(temp_stdout, file_framerate=file_framerate)
                    output_steps.append(output)
                    if print_output:
                        remaining_frames = frame_count - output.frame
                        if any([x.fps > 0 for x in output_steps]):
                            average_eta = seconds_to_duration(
                                remaining_frames / (sum([x.fps for x in output_steps]) / len(output_steps))
                            )
                        else:
                            average_eta = "?"
                        log.debug("{} | Avg. ETA: {:8s}".format(output.create_log_string(frame_count), average_eta))

                    temp_stdout = []

                    if "progress=end" in process_stdout:
                        hit_end = True

    return_code = process.poll()
    return return_code, [x.strip() for x in stdout if x], output_steps
