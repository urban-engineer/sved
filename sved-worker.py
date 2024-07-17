import json
import math
import os
import pathlib
import platform
import pika
import requests
import shlex
import shutil
import subprocess
import time

from utils import config
from utils import ffmpeg
from utils import ffprobe
from utils import log
from utils import metrics
from utils import mkvtoolnix


# TODO: fix heartbeat / "rabbitmq closes connection too early because these are long af" issue
# TODO: Progress indicators for download speed/completion ETA
# TODO: If we get a 404 when querying a task, just mark it complete and move on.

# (https://github.com/pika/pika/blob/0.12.0/examples/basic_consumer_threaded.py)
# Looks like basically defining a thread and running the task in the thread,
# while the "main" threat is sending heartbeats

# (additional thread: https://github.com/pika/pika/issues/1104)


def _format_size(size_bytes: int) -> str:
    """
    Return a string representing the provided byte count with the largest decimal unit.
    For example:
     * 1000 -> 1KB
     * 2000000 -> 2MB
     * 3000000000 -> 3GB
     * etc.

    :param size_bytes: number of bytes
    :return: string representing a shorter form of the provided bytes
    """
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "{}{}".format(s, size_name[i])


def _get_hostname() -> str:
    """
    Get the hostname as defined in the environment variable HOSTNAME

    :return: value of hostname environment variable
    """
    return os.environ.get("HOSTNAME", platform.node())


def _get_temp_work_directory() -> pathlib.Path:
    """
    Get the temporary directory for working files as defined by the environment variable WORKDIR

    :return: temp directory as a path
    """
    temp_directory = pathlib.Path(os.environ.get("WORKDIR", "sved-workdir"))
    if temp_directory.is_absolute():
        return temp_directory.resolve()
    else:
        return pathlib.Path.cwd().joinpath(temp_directory).resolve()


def _run_ffmpeg_command(command: str, frame_count: int, file_name: str,
                        callback_channel: pika.adapters.blocking_connection.BlockingChannel,
                        file_framerate: float = None, report_to_sved=False, detail_url: str = None) -> None:
    """
    Run an ffmpeg command.  Basically just the subprocess_handler run_command function,
    but with additional logic for handling ffmpeg output & sending status updates to the SVED manager.

    :param command: command to run to encode a file
    :param frame_count:
    :param file_name:
    :param callback_channel: channel to send messages back to rabbitmq, to keep it from thinking we've disconnected
    :param file_framerate: optional parameter, provide this to calculate speed if ffmpeg returning 'N/A'
    :param report_to_sved: flag, whether to send updates to sved (if detail_url is defined)
    :param detail_url: URL to send updates to if report_to_sved is True
    :return: None
    """
    stdout = []
    ffmpeg_output_parts = []
    output_steps = []
    in_progress = False  # Used so we can ignore output before we start running the task
    hit_end = False

    start_time = time.time()

    log.debug(command)
    process = subprocess.Popen(
        shlex.split(command),
        universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="backslashreplace"
    )

    while True:
        output = process.stdout.readline().strip()
        if output == "" and process.poll() is not None:
            break

        # Sending heartbeats while running long tasks
        if int(time.time()) % 10 == 0:
            callback_channel.connection.process_data_events()

        stdout.append(output)
        if output and not hit_end:
            if not in_progress and "frame=" in output:
                in_progress = True

            if in_progress and "=" in output and output.count("=") == 1:
                if output.startswith("["):
                    if "frame=" in output:
                        ffmpeg_output_parts.append(output.strip().split("] ")[1])
                    continue
                if " " in output.strip().split("=")[0]:
                    continue

                ffmpeg_output_parts.append(output)

                if "progress=" in output:
                    output_step = ffmpeg.format_ffmpeg_output(ffmpeg_output_parts, file_framerate=file_framerate)
                    output_steps.append(output_step)

                    remaining_frames = frame_count - output_step.frame
                    if any([x.fps > 0 for x in output_steps]):
                        average_eta = remaining_frames / (sum([x.fps for x in output_steps]) / len(output_steps))
                        average_eta_string = ffmpeg.seconds_to_duration(average_eta)
                    else:
                        average_eta = -1
                        average_eta_string = "?"

                    log.debug(
                        "{} | Avg. ETA: {:8s}".format(output_step.create_log_string(frame_count), average_eta_string)
                    )
                    ffmpeg_output_parts = []

                    if any([x.fps > 0 for x in output_steps]):
                        average_fps = sum([x.fps for x in output_steps]) / len(output_steps)
                    else:
                        average_fps = 0

                    #  Send progress to SVED
                    if report_to_sved and detail_url:
                        data = {
                            "progress": output_step.get_frame_as_percentage(frame_count),
                            "fps": average_fps,
                            "eta": average_eta
                        }
                        try:
                            requests.post(detail_url, data=json.dumps(data), headers={"worker": _get_hostname()})
                        except requests.exceptions.ConnectionError:
                            log.warning("Could not send progress update to manager")

                    if "progress=end" in output:
                        hit_end = True

    return_code = process.poll()
    if return_code != 0:
        if stdout:
            log.debug(stdout)
        raise RuntimeError("ffmpeg on [{}] returned code [{}]".format(file_name, return_code))

    average_fps = sum([x.fps for x in output_steps]) / len(output_steps)
    log.debug("Execution time: [{}]s (average FPS: [{}])".format(round(time.time() - start_time, 2), average_fps))

    if report_to_sved and detail_url:
        data = {
            "fps": average_fps,
            "progress": 100.00,
            "eta": 0
        }
        try:
            requests.post(detail_url, data=json.dumps(data), headers={"worker": _get_hostname()})
        except requests.exceptions.ConnectionError:
            log.warning("Could not send completion update to manager")


def _encode_file_crf(input_file: pathlib.Path, output_file: pathlib.Path,
                     detail_url: str, crf: int, profile: dict,
                     callback_channel: pika.adapters.blocking_connection.BlockingChannel) -> pathlib.Path:
    file_info = ffprobe.get_file_info(input_file)
    encode_command, output_file = ffmpeg.create_crf_command(
        input_file, output_path=output_file,
        codec=profile["codec"], crf=crf,
        preset=profile["encoder_preset"], tune=profile.get("encoder_tune", None)
    )

    data = {
        "progress": 0.0,
        "encode_type": "crf",
        "encode_value": crf
    }
    try:
        requests.post(detail_url, data=json.dumps(data), headers={"worker": _get_hostname()})
    except requests.exceptions.ConnectionError:
        log.warning("Could not send completion update to manager")

    try:
        _run_ffmpeg_command(
            encode_command, frame_count=file_info.frames, file_name=input_file.name,
            callback_channel=callback_channel, file_framerate=float(eval(file_info.video_stream["r_frame_rate"])),
            report_to_sved=True, detail_url=detail_url
        )
    except Exception as e:
        input_file.unlink(missing_ok=True)
        output_file.unlink(missing_ok=True)
        raise e

    if not output_file.exists():
        raise RuntimeError("Encoding succeeded but the file doesn't exist!")

    log.debug("Encoded file size: [{}]".format(_format_size(output_file.stat().st_size)))
    return output_file


def _encode_file_two_pass(input_file: pathlib.Path, output_file: pathlib.Path,
                          detail_url: str, profile: dict,
                          callback_channel: pika.adapters.blocking_connection.BlockingChannel) -> pathlib.Path:
    file_info = ffprobe.get_file_info(input_file)
    file_bitrate = ffmpeg.get_bitrate_for_scene(input_file)
    analyze_command, encode_command, output_file = ffmpeg.create_two_pass_command(
        input_file, output_path=output_file,
        codec=profile["codec"], bitrate=file_bitrate,
        preset=profile["encoder_preset"], tune=profile.get("encoder_tune", None)
    )

    data = {
        "progress": 0.0,
        "encode_type": "abr",
        "encode_value": file_bitrate
    }
    try:
        requests.post(detail_url, data=json.dumps(data), headers={"worker": _get_hostname()})
    except requests.exceptions.ConnectionError:
        log.warning("Could not send completion update to manager")

    try:
        _run_ffmpeg_command(
            analyze_command, frame_count=file_info.frames, file_name=input_file.name,
            callback_channel=callback_channel, file_framerate=float(eval(file_info.video_stream["r_frame_rate"])),
            report_to_sved=False
        )
        _run_ffmpeg_command(
            encode_command, frame_count=file_info.frames, file_name=input_file.name,
            callback_channel=callback_channel, file_framerate=float(eval(file_info.video_stream["r_frame_rate"])),
            report_to_sved=True, detail_url=detail_url
        )
    except Exception as e:
        input_file.unlink(missing_ok=True)
        output_file.unlink(missing_ok=True)
        raise e

    if not output_file.exists():
        raise RuntimeError("Encoding succeeded but the file doesn't exist!")

    log.debug("Encoded file size: [{}]".format(_format_size(output_file.stat().st_size)))
    return output_file


def download_file(url: str, file_name: str) -> pathlib.Path:
    """
    Download the file from the provided URL and save it to the temporary work directory with the given filename

    :param url: URL of a file to download
    :param file_name: string to name the file
    :return: path to the downloaded file
    """
    local_file_path = _get_temp_work_directory().joinpath(file_name)
    log.debug("Downloading file from [{}] to [{}]".format(url, local_file_path))
    local_file_path.parent.mkdir(exist_ok=True, parents=True)

    # TODO: catch connection reset by peer error
    # (triggered by restarting the webserver while a file is downloading)
    while True:
        try:
            with requests.get(url, stream=True, headers={"worker": _get_hostname()}) as response:
                if response.status_code != 200:
                    log.warning("Could not connect to manager at [{}]; retrying in 30s".format(url))
                    time.sleep(30)
                    continue
                with open(local_file_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                break
        except (ConnectionResetError, requests.exceptions.ChunkedEncodingError) as ce:
            if "connection reset by peer" in str(ce):
                log.warning("Lost connection with manager; sleeping 30s and retrying")
                time.sleep(30)

    local_file_path.chmod(0o777)
    log.debug("Download complete, downloaded size: [{}]".format(_format_size(local_file_path.stat().st_size)))
    return local_file_path


def encode_file(input_file: pathlib.Path, profile: dict, detail_url: str,
                callback_channel: pika.adapters.blocking_connection.BlockingChannel) -> (pathlib.Path, int, int):
    crf = profile["encode_value"]

    output_file = input_file.with_name("{}_compressed.mkv".format(input_file.stem))

    if profile["encode_type"] == "abr":
        output_file = _encode_file_two_pass(
            input_file=input_file, output_file=output_file,
            detail_url=detail_url, profile=profile, callback_channel=callback_channel
        )
    else:
        output_file = _encode_file_crf(
            input_file=input_file, output_file=output_file,
            detail_url=detail_url, crf=crf, profile=profile, callback_channel=callback_channel
        )

    mkvtoolnix.add_media_statistics(output_file)
    compressed_file_passes_scene_rules = ffmpeg.passes_scene_rules(input_file, output_file)
    while not compressed_file_passes_scene_rules:
        log.warning("Output does not pass scene rules")
        # TODO: send a request to the manager and track what encode we're on (e.g. attempt 3, attempt 4, etc.)
        if crf == 24:
            log.debug("Reached max CRF of 24; Encoding using ABR 2 Pass")
            output_file = _encode_file_two_pass(
                input_file=input_file, output_file=output_file,
                detail_url=detail_url, profile=profile, callback_channel=callback_channel
            )
            break
        else:
            crf += 1
            log.debug("Attempting an encode at [{}]".format(crf))
            output_file = _encode_file_crf(
                input_file=input_file, output_file=output_file,
                detail_url=detail_url, crf=crf, profile=profile, callback_channel=callback_channel
            )

        mkvtoolnix.add_media_statistics(output_file)
        compressed_file_passes_scene_rules = ffmpeg.passes_scene_rules(input_file, output_file)

    ffmpeg.delete_two_pass_logs(pathlib.Path.cwd())
    mkvtoolnix.add_media_statistics(output_file)

    return output_file


def upload_file(url: str, file_path: pathlib.Path) -> None:
    log.info("Uploading [{}] to [{}]".format(str(file_path), url))
    headers = {
        "worker": _get_hostname(),
        "size": str(file_path.stat().st_size)
    }
    while True:
        request = None
        try:
            # Streaming upload, doing it this way keeps the worker from
            # loading the entire file in memory before sending the POST request.
            with file_path.open("rb") as f:
                request = requests.post(url, data=f, headers=headers, stream=True)
                if request.status_code != 200:
                    pathlib.Path("file.html").write_text(request.text)

            break
        except requests.exceptions.ConnectionError:
            log.warning("Could not connect to manager at [{}]; retrying in 30s".format(url))

        if request and request.status_code != 200:
            log.warning("POST to [{}] with file returned code [{}]; retrying in 30s".format(url, request.status_code))
        time.sleep(30)


def calculate_metrics(reference_file: pathlib.Path, compressed_file: pathlib.Path,
                      calculate_psnr: bool, calculate_ms_ssim: bool,
                      neg_mode: bool, subsample_rate: int,
                      detail_url: str,
                      callback_channel: pika.adapters.blocking_connection.BlockingChannel) -> pathlib.Path:
    pathlib.Path("report.json").unlink(missing_ok=True)

    metrics_command = metrics.create_metrics_command(
        reference_file, compressed_file,
        neg_mode=neg_mode, subsample_rate=subsample_rate,
        psnr=calculate_psnr, ms_ssim=calculate_ms_ssim
    )

    file_info = ffprobe.get_file_info(reference_file)
    _run_ffmpeg_command(
        metrics_command,
        frame_count=file_info.frames, file_name=reference_file.name,
        callback_channel=callback_channel, file_framerate=float(eval(file_info.video_stream["r_frame_rate"])),

        report_to_sved=True, detail_url=detail_url
    )

    report_file = _get_temp_work_directory().joinpath("report.json")
    shutil.move(pathlib.Path("report.json"), report_file)

    return report_file


def callback(callback_channel: pika.adapters.blocking_connection.BlockingChannel, method: pika.spec.Basic.Deliver,
             properties: pika.spec.BasicProperties, body: bytes) -> None:

    # Get the message and do work
    decoded_message = json.loads(body.decode())

    task_type = decoded_message.get("type", "")
    log.info("Task [{}] [{}] pulled from queue, beginning processing".format(task_type, decoded_message["id"]))

    response = requests.get(decoded_message["url"])
    if response.status_code != 200:
        log.warning(
            "Received status code [{}] from request to [{}]".format(response.status_code, decoded_message["url"])
        )
        if response.text:
            if "<html" in response.text:
                html_file = _get_temp_work_directory().joinpath("error.html")
                log.warning("Received HTML response, printing to [{}]".format(html_file))
                html_file.parent.mkdir(exist_ok=True, parents=True)
                with html_file.open("w") as f:
                    f.write(response.text)
            else:
                log.debug("Response text: [{}]".format(response.text))
        raise RuntimeError("Request to [{}] returned code [{}]".format(decoded_message["url"], response.status_code))

    task_information = response.json()

    if task_type == "encode":
        input_file = download_file(
            task_information["encode_task_file_url_field"],
            task_information["source_file"]["name"]
        )

        profile = task_information["profile"]
        profile["encode_type"] = task_information["encode_type"]
        profile["encode_value"] = task_information["encode_value"]

        output_file = encode_file(input_file, profile, decoded_message["url"], callback_channel)
        upload_file(task_information["encode_task_file_url_field"], output_file)

    elif task_type == "metrics":
        file_stem = task_information["source_file"]["name"].split(".mkv")[0]
        reference_file = download_file(
            task_information["source_file_url_field"], "{}_reference.mkv".format(file_stem)
        )
        compressed_file = download_file(
            task_information["compressed_file_url_field"], "{}_compressed.mkv".format(file_stem)
        )

        metrics_report_file = calculate_metrics(
            reference_file=reference_file,
            compressed_file=compressed_file,
            calculate_psnr=task_information["psnr"], calculate_ms_ssim=task_information["ms_ssim"],
            neg_mode=task_information["neg_mode"], subsample_rate=task_information["subsample_rate"],
            detail_url=decoded_message["url"],
            callback_channel=callback_channel
        )

        upload_file(task_information["report_data_url"], metrics_report_file)

        # TODO: upload worst frame(s) to manager
    else:
        raise ValueError("Message in queue has unexpected task type: [{}]".format(task_type))

    log.debug("Deleting input and output files")
    shutil.rmtree(_get_temp_work_directory())

    # Acknowledge the completed work, removing it from the rabbitmq queue
    callback_channel.basic_ack(delivery_tag=method.delivery_tag)
    log.info("Task [{}] [{}] processed; waiting for new tasks".format(task_type, decoded_message["id"]))


if __name__ == "__main__":
    # Setup connection
    connection = pika.BlockingConnection(pika.ConnectionParameters(config.load_rabbitmq_config()["broker"]))
    channel = connection.channel()

    # Don't let rabbitmq send more than one message to a worker at a time.
    channel.basic_qos(prefetch_count=1)

    # Setup to receive messages
    channel.basic_consume(queue=config.load_rabbitmq_config()["queue"], auto_ack=False, on_message_callback=callback)

    log.info("Ready to receive work!")

    # Infinite loop of waiting for messages
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        log.debug("Interrupted")
        connection.close()
