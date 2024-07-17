import datetime
import json

from django.conf import settings
from django.db import models
from django.urls import reverse


########################################################################################################################
# Models
########################################################################################################################
class Profile(models.Model):
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    codec = models.TextField()  # `libx264` or `libx265` at this time.
    encode_type = models.CharField(max_length=3)  # `abr` or `crf`
    encode_value = models.IntegerField()
    encoder_preset = models.CharField(max_length=16)
    encoder_tune = models.TextField(blank=True)
    additional_arguments = models.TextField(blank=True)
    keep_original_main_audio = models.BooleanField()

    def __str__(self):
        return self.name

    def __repr__(self):
        # TODO: dump all information into this.
        return json.dumps(self.__dict__)


class EncodeTask(models.Model):
    # TODO: a status for first pass of a two-pass encode
    class TaskStatus(models.IntegerChoices):
        CREATED = 0
        QUEUED = 1
        DOWNLOADING = 2
        IN_PROGRESS = 3
        UPLOADING = 4
        COMPLETE = 5

    source_file = models.ForeignKey(
        'distributor.File',
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_source_related",
        related_query_name="%(app_label)s_%(class)s_source_files"
    )
    compressed_file = models.ForeignKey(
        'distributor.File',
        on_delete=models.CASCADE, default=None, null=True,
        related_name="%(app_label)s_%(class)s_compressed_related",
        related_query_name="%(app_label)s_%(class)s_compressed_files"
    )
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)

    # These are inherited from the profile.  However, they can be changed if the encode does not match the scene rules.
    # For example, if encoding a 1080p video at CRF 17 results in too large of a file, it'll be re-encoded at CRF 18.
    # Or if it hits 25 to reach 60% goal, then it will switch to 2-pass ABR and set bitrate to 60% source bitrate.
    encode_type = models.CharField(max_length=3, null=True)  # `abr` or `crf`
    encode_value = models.IntegerField(null=True)

    # These are for progress monitoring, and can be ignored once the encode is complete.
    worker = models.CharField(max_length=128, null=True)
    status = models.IntegerField(choices=TaskStatus.choices, default=TaskStatus.CREATED)
    progress = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    encode_framerate = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    seconds_remaining = models.IntegerField(null=True)

    creation_datetime = models.DateTimeField(auto_now_add=True)
    encode_start_datetime = models.DateTimeField(null=True)
    encode_end_datetime = models.DateTimeField(null=True)

    class Meta:
        verbose_name = "Encode Task"

    def __str__(self):
        return "{} ({}) [{}]".format(str(self.source_file), self.profile, self.status)

    def __repr__(self):
        return "[{}] {} ({} - {} @ {}) [{}]".format(
            self.pk, str(self.source_file), self.profile, self.encode_type.upper(), self.encode_value, self.status
        )

    def get_encode_rate(self, decimal_places: int = 2) -> float:
        return round(float(self.encode_framerate) / float(self.source_file.frame_rate), decimal_places)

    def get_remaining_duration(self) -> str:
        minutes, seconds = divmod(self.seconds_remaining, 60)
        hours, minutes = divmod(minutes, 60)
        return "{}:{}:{}".format(str(hours).zfill(2), str(minutes).zfill(2), str(seconds).zfill(2))

    def get_encode_task_url(self, is_secure: bool = False) -> str:
        """
        Get the URL for detail about the encode task

        :param is_secure: whether we're using https or not
        :return: URL serving the encode task information
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("encodes:api-task-detail", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("encodes:api-task-detail", args=(self.pk,)))

    def get_encode_task_file_url(self, is_secure: bool = False):
        """
        Get the URL for detail about the encode task

        :param is_secure: whether we're using https or not
        :return: URL serving the encode task information
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("encodes:api-task-file", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("encodes:api-task-file", args=(self.pk,)))
