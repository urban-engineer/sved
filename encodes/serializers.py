from rest_framework import serializers

import distributor.serializers
import encodes.models


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = encodes.models.Profile
        fields = "__all__"


class EncodeTaskSerializer(serializers.ModelSerializer):
    source_file = distributor.serializers.FileSerializer(many=False, read_only=True)
    compressed_file = distributor.serializers.FileSerializer(many=False, read_only=True)
    profile = ProfileSerializer(many=False, read_only=True)

    encode_task_file_url_field = serializers.ReadOnlyField(source="get_encode_task_file_url")

    class Meta:
        model = encodes.models.EncodeTask
        fields = [
            "id",
            "source_file",
            "compressed_file",
            "profile",
            "encode_type",
            "encode_value",
            "worker",
            "status",
            "progress",
            "encode_framerate",
            "seconds_remaining",
            "creation_datetime",
            "encode_start_datetime",
            "encode_end_datetime",
            "encode_task_file_url_field"
        ]
        read_only_fields = ["encode_task_file_url_field"]
