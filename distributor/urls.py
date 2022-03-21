from django.urls import path

from . import views

app_name = "distributor"
urlpatterns = [
    path("", views.index, name="index"),
    path("encodes/complete", views.completed_encodes, name="completed_encodes"),
    path("encodes/incomplete", views.incomplete_encodes, name="incomplete_encodes"),
    path("profiles/", views.profiles, name="profiles"),

    # API
    path("api/files/", views.api_file_list, name="api-file-list"),
    path("api/files/in-progress/", views.api_file_in_progress, name="api-file-in_progress"),
    path("api/files/<int:file_id>", views.api_file_detail, name="api-file-detail"),
    path("api/files/<int:file_id>/file", views.api_file, name="api-file"),
    path("api/files/<str:profile>/", views.api_profile_file_list, name="api-profile-file-list"),

    path("api/profiles/", views.api_profile_list, name="api-profile-list"),
    path("api/profiles/<int:profile_id>", views.api_profile_detail, name="api-profile-detail"),
]
