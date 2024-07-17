import pathlib
import typing

from utils import ffprobe
from utils import log
from utils import subprocess_handler


def add_media_statistics(file_path: pathlib.Path) -> None:
    log.debug("Adding statistics to [{}]".format(file_path))
    command_template = "mkvpropedit --add-track-statistics-tags \"{}\""
    command = command_template.format(str(file_path).replace("\\", "/").replace("\\'", "'"))

    code, out, err = subprocess_handler.run_command(command, print_output=False)
    if code != 0:
        if out:
            log.debug(out)
        if err:
            log.error(err)
        raise RuntimeError("Command [{}] returned code [{}]".format(command, code))


def add_media_statistics_if_necessary(file_path: pathlib.Path) -> None:
    file_information = ffprobe.get_file_info(file_path)

    if file_information.video_stream:
        stream_to_check = file_information.video_stream
    elif file_information.audio_streams:
        stream_to_check = file_information.audio_streams[0]
    elif file_information.subtitle_streams:
        stream_to_check = file_information.subtitle_streams[0]
    else:
        raise ValueError("File [{}] does not have video, audio, or subtitle streams".format(file_path))

    statistics_present = bool(stream_to_check.get("tags", {}).get("_STATISTICS_WRITING_APP", None))
    if not statistics_present:
        log.debug("File [{}] missing statistics from mkvtoolnix".format(file_path))
        add_media_statistics(file_path)


def change_audio_titles(file_path: pathlib.Path, new_titles: typing.List[str]) -> None:
    log.debug("Setting [{}] audio titles to [{}]".format(file_path.name, new_titles))

    command = [
        "\"{}\"".format(str("mkvpropedit")).replace("\\", "/"),
        "\"{}\"".format(str(file_path)).replace("\\", "/").replace("\\'", "'"),
    ]

    for i in range(len(new_titles)):
        command.append("--edit track:a{}".format(i + 1))
        command.append("--set \"name={}\"".format(new_titles[i]))

    code, out, err = subprocess_handler.run_command(" ".join(command), print_output=False)
    if code != 0:
        if out:
            log.debug(out)
        if err:
            log.error(err)
        raise RuntimeError("Command [{}] returned code [{}]".format(" ".join(command), code))


def unforce_subtitles(file_info: ffprobe.FFProbeFile) -> None:
    subs = [x for x in file_info.subtitle_streams]
    command_template = "mkvpropedit \"{}\" {}"
    track_commands = []
    sub_count = 1

    for sub in subs:
        if sub["disposition"]["forced"] == 1:
            track_commands.append("--edit track:s{} --set flag-forced=0".format(sub_count))
        sub_count += 1

    if len(track_commands) > 0:
        log.debug("Unforcing subtitles")
        command = command_template.format(str(file_info.path), " ".join(track_commands))
        code, out, err = subprocess_handler.run_command(command)
        if code != 0:
            if out:
                log.debug(out)
            if err:
                log.error(err)
            raise RuntimeError("Unforcing subtitles for [{}] returned code [{}]".format(file_info.path.name, code))
