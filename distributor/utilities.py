import concurrent.futures
import hashlib
import json
import pathlib
import typing

import distributor.models

from utils import ffprobe
from utils import log
from utils import mkvtoolnix


def _add_statistics_if_necessary():
    pass


def hash_file(file_path: pathlib.Path, block_size: int = 32768) -> str:
    """
    Get the SHA-1 hash of a file.  Picked this over others because it was the fastest of those tested
    (md5, sha1, sha256, and sha512)

    For future reference/testing, run these commands:
     * openssl speed md5 sha1 sha256 sha512
     * openssl speed -bytes 32768 md5 sha1 sha256 sha512
     * openssl speed -bytes 65536 md5 sha1 sha256 sha512

    :param file_path: path to file to hash
    :param block_size: number of bytes to process at once.  32768 is the point of diminishing returns.
    :return: file hash as a string, 40 characters long
    """
    sha = hashlib.sha1()
    with file_path.open("rb") as file:
        file_buffer = file.read(block_size)
        while len(file_buffer) > 0:
            sha.update(file_buffer)
            file_buffer = file.read(block_size)
    return sha.hexdigest()


def create_file(file_path: pathlib.Path) -> typing.Optional[distributor.models.File]:
    # Yes, I am assuming that files with the same name are the same file.
    # It is possible for you to have two different files named "video.mkv" (at different times of course)
    # and they have different stats.
    # However: don't do that.

    # file = distributor.models.File.objects.filter(name=file_path.name, directory=str(file_path.parent)).first()
    # if file:
    #     return file

    mkvtoolnix.add_media_statistics_if_necessary(file_path)
    file_information = ffprobe.get_file_info(file_path)

    bits = int(file_information.format.get("size", 0)) * 8
    seconds = round(float(file_information.format.get("duration", 0)))

    # If file is being written to this location, ignore it
    if seconds != 0 and bits != 0:
        file_object, created = distributor.models.File.objects.get_or_create(
            name=file_path.name,
            directory=str(file_path.parent),
            size=int(file_information.format.get("size", 0)),
            duration=file_information.duration,
            frame_rate=round(eval(file_information.video_stream["avg_frame_rate"]), 3),
            frames=file_information.frames,
        )
        if not created:
            log.debug("[{}] exists in DB as [{}]".format(file_object.name.encode().decode(), file_object.pk))
        return file_object
    else:
        return None


def scan_files(files: typing.List[pathlib.Path]) -> typing.List[distributor.models.File]:
    files_information = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_file = {executor.submit(create_file, x): x for x in files}
        for future in concurrent.futures.as_completed(future_to_file):
            file_object = future.result()
            if file_object:
                files_information.append(file_object)

    return sorted(files_information, key=lambda k: k.name)


def scan_directory(directory: pathlib.Path) -> typing.List[distributor.models.File]:
    """
    Scan a directory and return File objects

    :param directory:
    :return:
    """
    mkv_files = [x for x in directory.rglob("*.mkv") if x.is_file() and x.name.endswith("mkv")]

    log.debug("Found [{}] files to scan in [{}]".format(len(mkv_files), directory))
    return scan_files(mkv_files)
