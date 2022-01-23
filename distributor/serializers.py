from rest_framework import serializers

import distributor.models


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = distributor.models.Profile
        fields = "__all__"


class FileSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name")

    class Meta:
        model = distributor.models.File
        fields = "__all__"
        # fields = (
        #     "id", "name", "profile_name", "status", "worker", "progress", "encode_fps", "eta",
        #     "creation_datetime", "encode_start_datetime", "encode_end_datetime"
        # )
