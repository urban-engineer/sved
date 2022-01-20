import json
import math
import os
import pathlib
import platform
import pika
import requests
import subprocess
import time

from utils import config
from utils import log


# TODO: fix heartbeat / "rabbitmq closes connection too early because these are long af" issue
# TODO: Progress indicators for download speed/completion ETA

# (https://github.com/pika/pika/blob/0.12.0/examples/basic_consumer_threaded.py)
# Looks like basically defining a thread and running the task in the thread,
# while the "main" threat is sending heartbeats

# (additional thread: https://github.com/pika/pika/issues/1104)


def _format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "{}{}".format(s, size_name[i])


def _get_hostname() -> str:
    return os.environ.get("HOSTNAME", platform.node())


def _get_temp_work_directory() -> pathlib.Path:
    return pathlib.Path(os.environ.get("WORKDIR", "")).resolve()


def download_file(url: str, file_name: str) -> pathlib.Path:
    log.debug("Downloading file from [{}]".format(url))
    local_file_path = _get_temp_work_directory().joinpath(file_name)

    # TODO: catch connection reset by peer error
    # (triggered by restarting the webserver while a file is downloading)
    while True:
        try:
            with requests.get(url, stream=True, headers={"worker": _get_hostname()}) as response:
                if response.status_code != 200:
                    log.warning("Could not connect to manager at [{}]; retrying in 30s".format(url))
                    time.sleep(30)
                    continue

                with open(file_name, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                break
        except (ConnectionResetError, requests.exceptions.ChunkedEncodingError) as ce:
            if "connection reset by peer" in str(ce):
                log.warning("Lost connection with manager; sleeping 30s and retrying")
                time.sleep(30)

    log.debug("Download complete, downloaded size: [{}]".format(_format_size(local_file_path.stat().st_size)))
    return local_file_path


def write_profile(profile: str) -> pathlib.Path:
    handbrake_profile_format = {
        "PresetList": [
            {
                "ChildrenArray": [json.loads(profile)],
                "Folder": True,
                "PresetName": "Custom",
                "PresetDescription": "",
                "Type": 0
            }
        ],
        "VersionMajor": 47,
        "VersionMicro": 0,
        "VersionMinor": 0
    }

    preset_file = _get_temp_work_directory().joinpath("presets.json")
    preset_file.unlink(missing_ok=True)
    preset_file.write_text(json.dumps(handbrake_profile_format, indent=2))

    return preset_file.resolve()


def encode_file(input_file: pathlib.Path, profile_name: str, profile_file: pathlib.Path, detail_url: str,
                callback_channel: pika.adapters.blocking_connection.BlockingChannel) -> (pathlib.Path, int, int):
    output_file = _get_temp_work_directory().joinpath("enc_{}".format(input_file.name))

    handbrake_command = [
        "HandBrakeCLI",
        "--preset-import-file", "{}".format(str(profile_file)),
        "-i", "{}".format(str(input_file)),
        "-o", "{}".format(str(output_file)),
        "-Z", "Custom/{}".format(profile_name)
    ]
    log.debug(handbrake_command)

    process = subprocess.Popen(
        handbrake_command,
        universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="backslashreplace"
    )

    start_time = time.time()
    current_time = int(time.time())

    average_fps = 0.0
    eta = -1

    all_output = []

    while True:
        process_stdout = process.stdout.readline()
        if process_stdout == "" and process.poll() is not None:
            break

        if process_stdout:
            all_output.append(process_stdout)

        if process_stdout and process_stdout.startswith("Encoding") and int(time.time()) != current_time:
            stdout = process_stdout.strip()
            log.debug(stdout)

            if int(time.time()) % 10 == 0:
                callback_channel.connection.process_data_events()

            if " %" in stdout:
                progress = float(stdout.split(" %")[0].split(", ")[1])

                if "fps, avg" in stdout:
                    average_fps = float(stdout.split("fps, avg ")[1].split()[0])
                    eta = int(stdout.split("ETA ")[1].split("h")[0]) * 60 * 60
                    eta += int(stdout.split("ETA ")[1].split("h")[1].split("m")[0]) * 60
                    eta += int(stdout.split("ETA ")[1].split("m")[1].split("s")[0])

                data = {
                    "fps": average_fps,
                    "progress": progress,
                    "eta": eta
                }
                try:
                    requests.post(detail_url, data=json.dumps(data), headers={"worker": _get_hostname()})
                except requests.exceptions.ConnectionError as ce:
                    log.warning("Could not send progress message to manager")

        current_time = int(time.time())

    return_code = process.poll()
    log.debug("Encode time: [{}]s (average FPS: [{}])".format(round(time.time() - start_time, 2), average_fps))

    if return_code == 0 and not output_file.exists():
        log.error("Encoding returned code 0 but the file doesn't exist!")
        return_code = -1

    if return_code != 0:
        log.error("Encoding returned code [{}]".format(return_code))
        log.debug("".join(all_output))
        input_file.unlink(missing_ok=True)
        output_file.unlink(missing_ok=True)
        raise RuntimeError("Something went wrong encoding [{}]".format(input_file.name))

    data = {
        "fps": average_fps,
        "progress": 100.00,
        "eta": 0
    }
    try:
        requests.post(detail_url, data=json.dumps(data), headers={"worker": _get_hostname()})
    except requests.exceptions.ConnectionError as ce:
        log.warning("Could not send progress message to manager")

    log.debug("Encoded file size: [{}]".format(_format_size(output_file.stat().st_size)))
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
            # Streaming upload, doing it this way keeps the worker from trying to store the entire file
            # in memory before sending the POST request.
            with file_path.open("rb") as f:
                request = requests.post(url, data=f, headers=headers, stream=True)

            break
        except requests.exceptions.ConnectionError as ce:
            log.warning("Could not connect to manager at [{}]; retrying in 30s".format(url))

        if request and request.status_code != 200:
            log.warning("POST to [{}] with file returned code [{}]; retrying in 30s".format(url, request.status_code))
        time.sleep(30)


def callback(callback_channel: pika.adapters.blocking_connection.BlockingChannel, method: pika.spec.Basic.Deliver,
             properties: pika.spec.BasicProperties, body: bytes) -> None:

    # Get the message and do work
    decoded_message = json.loads(body.decode())
    log.info("Received [{}] ({}); beginning processing".format(decoded_message["name"], decoded_message["id"]))

    input_file = download_file(decoded_message["file_url"], decoded_message["name"])
    presets_file = write_profile(decoded_message["profile"])
    output_file = encode_file(
        input_file, decoded_message["profile_name"], presets_file, decoded_message["file_detail_url"], callback_channel
    )
    upload_file(decoded_message["file_url"], output_file)

    log.debug("Deleting input and output files")
    input_file.unlink()
    output_file.unlink()
    presets_file.unlink()

    # Acknowledge the completed work, removing it from the rabbitmq queue
    callback_channel.basic_ack(delivery_tag=method.delivery_tag)
    log.debug("Task [{}] ({}) processed; waiting for new tasks".format(decoded_message["name"], decoded_message["id"]))


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
