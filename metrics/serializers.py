from rest_framework import serializers

import distributor.serializers
import metrics.models


class MetricTaskSerializer(serializers.ModelSerializer):
    source_file = distributor.serializers.FileSerializer(many=False, read_only=True)
    compressed_file = distributor.serializers.FileSerializer(many=False, read_only=True)
    report_data_url = serializers.ReadOnlyField(source="get_metrics_task_report_url")

    source_file_url_field = serializers.ReadOnlyField(source="get_source_file_url")
    compressed_file_url_field = serializers.ReadOnlyField(source="get_compressed_file_url")

    class Meta:
        model = metrics.models.MetricTask
        # fields = "__all__"
        fields = [
            "id",
            "source_file",
            "compressed_file",
            "worker",
            "status",
            "progress",
            "processing_framerate",
            "seconds_remaining",
            "creation_datetime",
            "analyze_start_datetime",
            "analyze_end_datetime",
            "report_data_url",
            "psnr",
            "ms_ssim",
            "vmaf",
            "neg_mode",
            "subsample_rate",
            "source_file_url_field",
            "compressed_file_url_field"
        ]
        read_only_fields = ["report_data_url"]
