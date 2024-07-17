from django.contrib import admin

import encodes.models


########################################################################################################################
# Admin objects
########################################################################################################################
class EncodeTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id", "source_file", "profile", "worker", "encode_type", "encode_value", "status", "progress",
        "encode_framerate", "seconds_remaining", "creation_datetime", "encode_start_datetime", "encode_end_datetime"
    )
    ordering = ("pk", )


class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name", "description",
        "codec", "encode_type", "encode_value", "encoder_preset", "encoder_tune",
        "additional_arguments",
        "keep_original_main_audio"
    )
    ordering = ("pk", )


########################################################################################################################
# Default Admin models
########################################################################################################################
admin.site.register(encodes.models.EncodeTask, EncodeTaskAdmin)
admin.site.register(encodes.models.Profile, ProfileAdmin)
