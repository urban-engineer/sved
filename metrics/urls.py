from django.urls import include, path

from . import views

app_name = "metrics"

api_patterns = [
    # Since we don't get metrics per-frame calculated, just send the output file and have the server parse it.
    # API should not respond with the metrics of every frame.
    # Should be able to ask for the 'worst' frame(s) (server should check the pooled metrics, then do a lookup)

    # api-task: GET for information on task (includes pooled metrics once available), POST to send results to DB
    # api-task-parameters: GET for parameters to execute
    # api-task-report: GET for metrics data (if available), POST to upload metrics data to DB
    # api-task-worst: returns frame number & metrics of lowest qualities frame(s).

    path("", views.api_task_list, name="api-task-list"),
    path("in-progress/", views.api_tasks_in_progress, name="api-tasks-in-progress"),
    path("<int:task_pk>/", views.api_task_detail, name="api-task-detail"),
    path("<int:task_pk>/files/source", views.api_task_source, name="api-task-source"),
    path("<int:task_pk>/files/compressed", views.api_task_compressed, name="api-task-compressed"),
    path("<int:task_pk>/report/", views.api_report_data, name="api-task-report"),
    path("<int:task_pk>/worst/", views.api_task_worst, name="api-task-worst"),
]

browser_patterns = [
    # task-detail: GET for human-readable summary of metrics.  Allow for deleting files and regenerating comparisons
    # task-compare: GET for nine random frames to compare against.  Clicking on any goes to task-compare-specific:frame
    # task-compare-specific: GET for metric comparison of specific frame.
    # task-compare-worst: GET for metric comparison of worst frame(s).
    # tasks-incomplete: GET for all metrics tasks currently in progress

    path("<int:task_pk>/", views.task_detail, name="task-detail"),
    path("<int:task_pk>/compare/", views.task_compare, name="task-compare"),
    path("<int:task_pk>/compare/<int:frame_number>/", views.task_compare_specific, name="task-compare-specific"),
    path("<int:task_pk>/compare/worst/", views.task_compare_worst, name="task-compare-worst"),
    path("in-progress/", views.tasks_incomplete, name="tasks-incomplete"),
    path("completed/", views.tasks_completed, name="tasks-completed")
]

urlpatterns = [
    path("", views.index, name="index"),

    # Normal
    path("ingest/", views.ingest, name="ingest"),
    path("task/", include(browser_patterns)),

    # API - Tasks
    path("api/", include(api_patterns))
]
