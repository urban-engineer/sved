from django.contrib import admin

# Register your models here.
import metrics.models


########################################################################################################################
# Admin objects
########################################################################################################################
class MetricTaskAdmin(admin.ModelAdmin):
    # TODO: link to source and compressed file?  index of each, at least.
    list_display = (
        "id", "source_file", "compressed_file", "psnr", "ms_ssim", "vmaf", "neg_mode", "subsample_rate",
        "worker", "status", "progress", "processing_framerate", "seconds_remaining",
        "creation_datetime", "analyze_start_datetime", "analyze_end_datetime"
    )


class FrameAdmin(admin.ModelAdmin):
    list_display = (
        "id", "task", "frame_number", "psnr", "ms_ssim", "vmaf"
    )


class PooledPSNRAdmin(admin.ModelAdmin):
    list_display = (
        "id", "task", "min", "max", "mean", "harmonic_mean"
    )


class PooledMSSSIMAdmin(admin.ModelAdmin):
    list_display = (
        "id", "task", "min", "max", "mean", "harmonic_mean"
    )


class PooledVMAFAdmin(admin.ModelAdmin):
    list_display = (
        "id", "task", "min", "max", "mean", "harmonic_mean"
    )


########################################################################################################################
# Default Admin models
########################################################################################################################
admin.site.register(metrics.models.MetricTask, MetricTaskAdmin)
admin.site.register(metrics.models.Frame, FrameAdmin)
admin.site.register(metrics.models.PooledPSNR, PooledPSNRAdmin)
admin.site.register(metrics.models.PooledMSSSIM, PooledMSSSIMAdmin)
admin.site.register(metrics.models.PooledVMAF, PooledVMAFAdmin)
