from django.urls import path

from . import views

app_name = "distributor"

urlpatterns = [
    path("", views.index, name="index"),

    #######
    # API #
    #######

    # API - Files
    path("api/files/", views.api_file_list, name="api-file-list"),
    path("api/files/<int:file_id>/file", views.api_file, name="api-file"),
]
