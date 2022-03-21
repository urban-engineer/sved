import pathlib

from django.db import models


########################################################################################################################
# Helpers
########################################################################################################################


########################################################################################################################
# Models
########################################################################################################################
class Profile(models.Model):
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    definition = models.TextField()

    def __str__(self):
        return self.name

    def __repr__(self):
        self.__str__()


class File(models.Model):
    name = models.CharField(max_length=256)
    path = models.CharField(max_length=256)
    duration = models.DecimalField(max_digits=9, decimal_places=3)
    frame_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0.0)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    status = models.TextField()
    worker = models.CharField(max_length=128, blank=True)
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    encode_fps = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    eta = models.IntegerField(default=-1)
    creation_datetime = models.DateTimeField(default="1970-01-01 00:00:00Z")
    encode_start_datetime = models.DateTimeField(default="1970-01-01 00:00:00Z")
    encode_end_datetime = models.DateTimeField(default="1970-01-01 00:00:00Z")

    def __str__(self):
        return self.name

    def __repr__(self):
        return "{}\\{} ({})".format(self.path, self.name, self.profile)

    def full_path(self) -> pathlib.Path:
        return pathlib.Path(self.path, self.name)
