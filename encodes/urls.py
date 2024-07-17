from django.urls import path

from . import views

app_name = "encodes"

urlpatterns = [
    path("", views.index, name="index"),

    # Normal - Tasks
    path("ingest/", views.ingest, name="ingest"),
    path("tasks/complete/", views.completed_tasks, name="completed-tasks"),
    path("tasks/incomplete/", views.incomplete_tasks, name="incomplete-tasks"),

    # Normal - Profiles
    path("profiles/", views.profiles, name="profiles"),

    # Normal - Worker Stats
    path("workers/", views.worker_stats, name="worker-stats"),

    # API - Tasks
    path("api/tasks/", views.api_task_list, name="api-task-list"),
    path("api/tasks/in-progress/", views.api_tasks_in_progress, name="api-tasks-in-progress"),
    path("api/tasks/<int:task_pk>", views.api_task_detail, name="api-task-detail"),
    path("api/tasks/<int:task_pk>/file", views.api_task_file, name="api-task-file"),

    # API - Profiles
    path("api/profiles/", views.api_profile_list, name="api-profile-list"),
    path("api/profiles/<int:profile_pk>", views.api_profile_detail, name="api-profile-detail"),
    path("api/profiles/<int:profile_pk>/tasks", views.api_profile_file_list, name="api-profile-file-list"),
]
