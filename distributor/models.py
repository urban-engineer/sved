import datetime
import math
import pathlib

from django.conf import settings
from django.db import models
from django.urls import reverse


########################################################################################################################
# Private Helpers
########################################################################################################################
def _format_bytes(file_size: int):
    if file_size and file_size > 0:
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(file_size, 1024)))
        s = round(file_size / math.pow(1024, i), 2)
        return "{}{}".format(s, size_name[i])
    else:
        return "0B"


########################################################################################################################
# Models
########################################################################################################################
class File(models.Model):
    name = models.CharField(max_length=256)
    directory = models.CharField(max_length=256)
    size = models.IntegerField(null=True)
    duration = models.DecimalField(max_digits=9, decimal_places=3, null=True)
    frame_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    frames = models.IntegerField(null=True)

    def __str__(self):
        return "{} [{}]".format(self.name, self.pk)

    def __repr__(self):
        return "{}\\{} [{}]".format(self.directory, self.name, self.pk)

    def get_full_path(self) -> pathlib.Path:
        return pathlib.Path(self.directory, self.name)

    def get_file_url(self, is_secure: bool = False) -> str:
        """
        Get the URL for the actual file of a file ID

        :param is_secure: whether we're using https or not
        :return: URL serving the file itself
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("distributor:api-file", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("distributor:api-file", args=(self.pk,)))

    def get_size_formatted(self) -> str:
        return _format_bytes(self.size)

    def get_bitrate(self) -> int:
        return int((self.size * 8) // self.duration)

    def get_bitrate_formatted(self) -> str:
        return _format_bytes(self.get_bitrate()).replace("B", "b") + "/s"

    def seconds_to_duration(self) -> str:
        # Formatting as XX:YY:ZZ, it currently normally returns X:YY:ZZ, so just add a 0 if necessary.
        # And if it's over a day long (WHY), figure out how many days it is and get it looking "nice"
        delta = str(datetime.timedelta(seconds=round(self.duration)))
        if self.duration >= 86400:
            days = delta.split(", ")[0].split(" ")[0]
            hours, minutes, seconds = delta.split(", ")[1].split(":")
            hours = int(hours) + int(days) * 24
            return "{:2}:{:2}:{:2}".format(str(hours), str(minutes), str(seconds))
        else:
            delta_split = [x.zfill(2) for x in delta.split(":")]
            return "{:2}:{:2}:{:2}".format(delta_split[0], delta_split[1], delta_split[2])
