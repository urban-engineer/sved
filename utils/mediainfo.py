import json
import pathlib

from utils import log
from utils import subprocess_handler


class MediaInfoFile:
    def __init__(self, file: pathlib.Path):
        command = "mediainfocli --Output=JSON \"{}\"".format(file)
        code, out, err = subprocess_handler.run_command(command, print_output=False)
        if code != 0:
            if out:
                log.debug(out)
            if err:
                log.error(err)
            raise RuntimeError("mediainfocli on [{]] returned code [{}]".format(file.name, code))

        self.formatted_return = json.loads("\n".join(out))

        self.general_info = [x for x in self.formatted_return["media"]["track"] if x["@type"] == "General"][0]
        self.audio_streams = [x for x in self.formatted_return["media"]["track"] if x["@type"] == "Audio"]
        self.subtitle_streams = [x for x in self.formatted_return["media"]["track"] if x["@type"] == "Text"]

        video_streams = [x for x in self.formatted_return["media"]["track"] if x["@type"].lower() == "video"]

        self.thumbnail_streams = [x for x in video_streams if "image" in x.get("extra", {}).get("MIMETYPE", "").lower()]
        thumbnail_ids = [int(x.get("ID", -9999)) for x in self.thumbnail_streams]
        real_video_streams = [x for x in video_streams if int(x.get("ID", -9999)) not in thumbnail_ids]

        if len(real_video_streams) != 1:
            raise RuntimeError("Expected 1 video stream; got [{}]".format(len(real_video_streams)))
        else:
            self.video_stream = real_video_streams[0]

    def __repr__(self):
        return json.dumps(self.formatted_return)

    def __str__(self):
        return json.dumps(self.formatted_return, indent=2)


def get_frame_count(file_path: pathlib.Path) -> int:
    command = "mediainfocli --Inform=Video;%FrameCount% \"{}\"".format(file_path)
    code, out, err = subprocess_handler.run_command(command, print_output=False)
    if code != 0:
        if out:
            log.debug(out)
        if err:
            log.error(err)
        raise RuntimeError("mediainfocli on [{]] returned code [{}]".format(file_path.name, code))

    try:
        return int(out[0])
    except IndexError:
        raise RuntimeError("Could not get frame count from [{}]".format(file_path.name))


def get_media_info(file_path: pathlib.Path) -> MediaInfoFile:
    return MediaInfoFile(file_path)
