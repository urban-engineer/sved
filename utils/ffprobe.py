import json
import pathlib

from utils import log
from utils import mediainfo
from utils import subprocess_handler


class FFProbeFile:
    def __init__(self, file: pathlib.Path):
        self.path = file

        command = "ffprobe -v error -show_streams -show_format -of json \"{}\"".format(file)
        code, out, err = subprocess_handler.run_command(command, print_output=False)
        if code != 0:
            if out:
                log.debug(out)
            if err:
                log.error(err)
            raise RuntimeError("ffprobe on [{}] returned code [{}]".format(file.name, code))

        formatted_output = json.loads("\n".join(out))
        self.format: dict = formatted_output["format"]

        self.video_stream = None
        self.subtitle_streams = [x for x in formatted_output["streams"] if x.get("codec_type", "") == "subtitle"]
        self.audio_streams = [x for x in formatted_output["streams"] if x.get("codec_type", "") == "audio"]
        self.audio_streams = sorted(self.audio_streams, key=lambda x: x["index"])

        # Handling embedded thumbnails
        video_streams = [x for x in formatted_output["streams"] if x.get("codec_type", "").lower() == "video"]
        real_video_streams = []
        self.thumbnail_streams = []

        for stream in video_streams:
            tags = stream.get("tags", {})
            mimetypes = [tags.get("mimetype", "").lower(), tags.get("MIMETYPE", "").lower()]
            if any(["image" in x for x in mimetypes]):
                self.thumbnail_streams.append(stream)
            else:
                real_video_streams.append(stream)

        if len(real_video_streams) != 1:
            raise RuntimeError("Expected 1 video stream; got [{}]".format(len(real_video_streams)))
        else:
            self.video_stream = real_video_streams[0]

        self.height: int = int(self.video_stream["height"])
        self.width: int = int(self.video_stream["width"])

        try:
            self.duration: float = float(self.format["duration"])
        except KeyError as ke:
            if "duration" in str(ke):
                raise ValueError("File [{}] is not a video".format(file.name))

        # It's actually faster to get frame count with mediainfo than it is with ffprobe, so we're doing that
        # (1.5s vs 0.05s for local tests)

        self.frames: int = mediainfo.get_frame_count(file)

    def __str__(self):
        return_dict = self.__dict__
        return_dict["path"] = str(self.path)
        return json.dumps(return_dict)

    def __repr__(self):
        return "<FFProbeFile for {}".format(self.path.name)

    def get_video_bitrate(self):
        """
        Return the bitrate as recorded after running `mkvpropedit --add-track-statistics-tags <file>`

        :return: Bitrate of video stream, in Bytes Per Second
        """
        return int(self.video_stream.get("tags", {}).get("BPS", -1))


def get_file_info(file_path: pathlib.Path) -> FFProbeFile:
    return FFProbeFile(file_path)
