from django.contrib import admin

import distributor.models


# Customizing Admin Panel
class FileAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "duration", "profile", "status", "worker", "progress", "fps",
        "creation_datetime", "encode_start_datetime", "encode_end_datetime"
    )


########################################################################################################################
# Default Admin models
########################################################################################################################
admin.site.register(distributor.models.Profile)
admin.site.register(distributor.models.File, FileAdmin)
