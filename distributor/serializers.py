from rest_framework import serializers

import distributor.models


class FileSerializer(serializers.ModelSerializer):
    file_url_field = serializers.ReadOnlyField(source="get_file_url")
    file_detail_url_field = serializers.ReadOnlyField(source="get_file_detail_url")

    class Meta:
        model = distributor.models.File
        fields = [
            "id",
            "name",
            "size",
            "duration",
            "frame_rate",
            "frames",
            "file_url_field",
            "file_detail_url_field"
        ]
        read_only_fields = ["file_url_field", "file_detail_url_field"]
