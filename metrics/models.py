from django.conf import settings
from django.db import models
from django.urls import reverse


########################################################################################################################
# Models
########################################################################################################################
class MetricTask(models.Model):
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

    # Flags to enable calculating certain statistics
    psnr = models.BooleanField(default=True)
    ms_ssim = models.BooleanField(default=True)
    vmaf = models.BooleanField(default=True)

    # True to use the "No Enhancement Gain" model
    # (created for codec evaluation/"to assess the pure effect coming from compression")
    # False to use "default" mode which is supposed to assess compression & enhancement combined
    neg_mode = models.BooleanField(default=False)

    # Sample every X frames.  1 means all frames, 10 would be the 1st, 11th, 21st, etc.
    subsample_rate = models.IntegerField(default=1)

    # Monitoring information
    worker = models.CharField(max_length=128, blank=True)
    status = models.IntegerField(choices=TaskStatus.choices, default=TaskStatus.CREATED)
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    processing_framerate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    seconds_remaining = models.IntegerField(default=-1)

    creation_datetime = models.DateTimeField(auto_now_add=True)
    analyze_start_datetime = models.DateTimeField(null=True)
    analyze_end_datetime = models.DateTimeField(null=True)

    class Meta:
        verbose_name = "Metric Task"

    def get_metrics_task_url(self, is_secure: bool = False) -> str:
        """
        Get the URL for detail about the metrics task

        :param is_secure: whether we're using https or not
        :return: URL serving the metrics task information
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("metrics:api-task-detail", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("metrics:api-task-detail", args=(self.pk,)))

    def get_metrics_task_report_url(self, is_secure: bool = False) -> str:
        """
        Get the URL for GET/POST requests for the metrics task report data

        :param is_secure: whether we're using https or not
        :return: URL serving the metrics report data
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("metrics:api-task-report", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("metrics:api-task-report", args=(self.pk,)))

    def get_source_file_url(self, is_secure: bool = False):
        """
        Get the URL to access the source file

        :param is_secure: whether we're using https or not
        :return: URL serving the source file
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("metrics:api-task-source", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("metrics:api-task-source", args=(self.pk,)))

    def get_compressed_file_url(self, is_secure: bool = False):
        """
        Get the URL to access the compressed file

        :param is_secure: whether we're using https or not
        :return: URL serving the compressed file
        """
        request_host = "{}:{}".format(settings.MANAGER_ADDRESS, "8080")
        if is_secure:
            return "https://{}{}".format(request_host, reverse("metrics:api-task-compressed", args=(self.pk,)))
        else:
            return "http://{}{}".format(request_host, reverse("metrics:api-task-compressed", args=(self.pk,)))


class Frame(models.Model):
    task = models.ForeignKey(MetricTask, on_delete=models.CASCADE)
    frame_number = models.IntegerField()

    # Might not calculate these for each metric (though I can't imagine many scenarios where you wouldn't want to)
    psnr = models.DecimalField(max_digits=8, decimal_places=6, null=True)     # 0.000000 ->  60.000000
    ms_ssim = models.DecimalField(max_digits=7, decimal_places=6, null=True)  # 0.000000 ->   1.000000
    vmaf = models.DecimalField(max_digits=9, decimal_places=6, null=True)     # 0.000000 -> 100.000000


# So we can theoretically calculate all these once we have all the scores.
# However, by storing them in the DB, we don't have to repeatedly query thousands of rows to do simple operations.
# Note to self: Be sure to recalculate the values being provided since they'll all be loaded into memory.
# Can't hurt to confirm the VMAF library is giving us correct numbers.

class PooledPSNR(models.Model):
    task = models.OneToOneField(MetricTask, on_delete=models.CASCADE)

    min = models.DecimalField(max_digits=8, decimal_places=6)
    one_percent_min = models.DecimalField(max_digits=8, decimal_places=6)
    point_one_percent_min = models.DecimalField(max_digits=8, decimal_places=6)

    max = models.DecimalField(max_digits=8, decimal_places=6)

    mean = models.DecimalField(max_digits=8, decimal_places=6)
    harmonic_mean = models.DecimalField(max_digits=8, decimal_places=6)

    class Meta:
        verbose_name = "Pooled PSNR Metric"


class PooledMSSSIM(models.Model):
    task = models.OneToOneField(MetricTask, on_delete=models.CASCADE)

    min = models.DecimalField(max_digits=7, decimal_places=6)
    one_percent_min = models.DecimalField(max_digits=7, decimal_places=6)
    point_one_percent_min = models.DecimalField(max_digits=7, decimal_places=6)

    max = models.DecimalField(max_digits=7, decimal_places=6)

    mean = models.DecimalField(max_digits=7, decimal_places=6)
    harmonic_mean = models.DecimalField(max_digits=7, decimal_places=6)

    class Meta:
        verbose_name = "Pooled MS_SSIM Metric"


class PooledVMAF(models.Model):
    task = models.OneToOneField(MetricTask, on_delete=models.CASCADE)

    min = models.DecimalField(max_digits=9, decimal_places=6)
    one_percent_min = models.DecimalField(max_digits=9, decimal_places=6)
    point_one_percent_min = models.DecimalField(max_digits=9, decimal_places=6)

    max = models.DecimalField(max_digits=9, decimal_places=6)

    mean = models.DecimalField(max_digits=9, decimal_places=6)
    harmonic_mean = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        verbose_name = "Pooled VMAF Metric"
