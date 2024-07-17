import json
import pathlib

import django.core.handlers.wsgi
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import distributor.models
import distributor.utilities

import metrics.models
import metrics.serializers

from utils import config
from utils import log
from utils import rabbit_handler


########################################################################################################################
# Helpers
########################################################################################################################
def _queue_task(task: metrics.models.MetricTask, is_secure: bool = False) -> None:
    """
    Queue a task.  Creates and sends message to rabbitmq for processing by workers, then sets
    the task's status to Queued.

    :param task: task to queue
    :param is_secure: whether we're using https or not
    :return: None
    """
    message_data = {
        "type": "metrics",
        "id": task.id,
        "url": task.get_metrics_task_url(is_secure=is_secure)
    }

    log.info("Queuing Metrics Task [{}] - [{}]".format(task.pk, task.source_file.name))
    rabbit_handler.send_message(message_data)

    task.status = task.TaskStatus.QUEUED
    task.save()


def _get_lows(scores, low_type: str = "1%") -> float:
    if low_type == "1%":
        frame_count = len(scores) // 100
    elif low_type == "0.1%":
        frame_count = len(scores) // 1000
    else:
        raise ValueError("type should be \"1%\" or \"0.1%\"")

    # Catching an error where we have less than 100 or 1000 frames
    frame_count = max(frame_count, 1)

    return sum(sorted(scores)[0:frame_count]) / frame_count


########################################################################################################################
# User Views
########################################################################################################################
def index(request):
    distributor.utilities.scan_directory(config.load_input_directory())
    distributor.utilities.scan_directory(config.load_output_directory())

    reference_files = []
    for file in distributor.models.File.objects.filter(directory__iexact=str(config.load_input_directory())):
        if file.get_full_path().exists() and file.get_full_path().stat().st_size == file.size:
            reference_files.append(file)

    compressed_files = []
    for file in distributor.models.File.objects.filter(directory__istartswith=str(config.load_output_directory())):
        if file.get_full_path().exists() and file.get_full_path().stat().st_size == file.size:
            compressed_files.append(file)

    context = {
        "reference_files": sorted(reference_files, key=lambda k: k.name),
        "compressed_files": sorted(compressed_files, key=lambda k: k.name)
    }
    return render(request, "metrics/management.html", context)


def ingest(request):
    if request.method == "POST":
        reference_file = get_object_or_404(distributor.models.File, pk=request.POST.get("reference_file"))

        for file_id in request.POST.getlist("compressed_files"):
            log.debug("Creating metric task for file [{}]".format(file_id))
            compressed_file = get_object_or_404(distributor.models.File, pk=file_id)

            task = metrics.models.MetricTask.objects.create(
                source_file=reference_file,
                compressed_file=compressed_file,
                psnr=request.POST.get("psnr_switch", "off").lower() == "on",
                ms_ssim=request.POST.get("ms_ssim_switch", "off").lower() == "on",
                vmaf=request.POST.get("vmaf_switch", "off").lower() == "on",
                subsample_rate=request.POST.get("subsample_rate", 1),
            )
            _queue_task(task)

        return HttpResponseRedirect(reverse("metrics:tasks-incomplete"))
    else:
        return HttpResponse("This page only supports POST requests", status=405)


def tasks_incomplete(request):
    queued_statuses = [
        metrics.models.MetricTask.TaskStatus.CREATED,
        metrics.models.MetricTask.TaskStatus.QUEUED
    ]
    in_progress_statuses = [
        metrics.models.MetricTask.TaskStatus.DOWNLOADING,
        metrics.models.MetricTask.TaskStatus.IN_PROGRESS,
        metrics.models.MetricTask.TaskStatus.UPLOADING
    ]

    # We create the `job_status_list` object as an easy way to get the display string for each enum
    # in a simple way.  I'm not married to this, but it gets the job done.
    context = {
        "jobs_queued": metrics.models.MetricTask.objects.filter(status__in=queued_statuses),
        "jobs_in_progress": metrics.models.MetricTask.objects.filter(status__in=in_progress_statuses),
        "job_status": metrics.models.MetricTask.TaskStatus,
        "job_status_list": json.dumps([x.label for x in metrics.models.MetricTask.TaskStatus])
    }
    return render(request, "metrics/tasks/incomplete.html", context)


def tasks_completed(request):
    # TODO: Fix the template and make this show task information
    # Then work on the task detail page so you can see more detailed information
    completed_tasks = metrics.models.MetricTask.objects.filter(status=metrics.models.MetricTask.TaskStatus.COMPLETE)
    context = {
        "completed_tasks": completed_tasks,
    }
    return render(request, "metrics/tasks/completed.html", context)


def task_detail(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)


def task_compare(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)


def task_compare_specific(request, task_pk: int, frame_number: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)


def task_compare_worst(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)


########################################################################################################################
# API Views
########################################################################################################################
def api_task_list(request):
    if request.method != "GET":
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )

    tasks = metrics.models.MetricTask.objects.all()
    serializer = metrics.serializers.MetricTaskSerializer(tasks, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


def api_tasks_in_progress(request):
    tasks = metrics.models.MetricTask.objects.all().exclude(status=metrics.models.MetricTask.TaskStatus.COMPLETE)
    serializer = metrics.serializers.MetricTaskSerializer(tasks, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


@csrf_exempt
def api_task_detail(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)

    if request.method == "POST":
        progress_data = json.loads(request.body)
        worker = request.headers.get("Worker", None)

        if "progress" not in progress_data.keys():
            log.warning("Received POST to task detail view missing [progress] key")
            return JsonResponse({"error": "Missing data key [progress]"}, json_dumps_params={"indent": 2}, status=400)
        task.progress = progress_data.get("progress", 0)

        # FPS and ETA are optional, since for the first 5s of processing they're wildly inaccurate
        task.processing_framerate = progress_data.get("fps", 0.0)
        task.seconds_remaining = progress_data.get("eta", -1)

        if worker and worker != task.worker:
            log.warning(
                "Worker [{}] logged as processing [{}] but [{}] is sending updates".format(
                    task.worker, task.id, worker
                )
            )
            task.worker = worker

        if task.status != task.TaskStatus.IN_PROGRESS:
            task.status = task.TaskStatus.IN_PROGRESS

        task.save()
        return JsonResponse(
            {"message": "POST received successfully"},
            json_dumps_params={"indent": 2},
            status=200
        )
    elif request.method == "GET":
        serializer = metrics.serializers.MetricTaskSerializer(task)
        return_data = serializer.data.copy()
        return JsonResponse(return_data, safe=False, json_dumps_params={"indent": 2})

    return JsonResponse(
        {"error": "this endpoint only supports GET/POST requests, not [{}]".format(request.method)},
        json_dumps_params={"indent": 2},
        status=405
    )


@csrf_exempt
def api_report_data(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)

    if request.method == "POST":
        expected_file_size = int(request.headers.get("size", None))
        if not expected_file_size:
            log.error("POST request from worker missing [size] header")
            return JsonResponse(
                {"error": "missing size parameter in request body"},
                json_dumps_params={"indent": 2},
                status=400
            )

        # Why aren't we just using request.FILES, you ask?  Well, it's quite simple.
        # Because the worker is sending data in a funky stream, the file itself isn't available in
        # the FILES dict.  So we have to read it in a funky way, which is through the wsgi.input version.
        # This is probably suboptimal, however it works on my machine(s), so it works.

        uploaded_file: django.core.handlers.wsgi.LimitedStream = request.META.get("wsgi.input")
        if not uploaded_file:
            log.error("POST request from worker missing file")
            return JsonResponse(
                {"error": "no file in request"},
                json_dumps_params={"indent": 2},
                status=400
            )

        log.debug("Saving report of [{}] vs. [{}]".format(task.source_file.name, task.compressed_file.name))

        task.status = task.TaskStatus.UPLOADING
        task.save()

        report_file = pathlib.Path("report-{}.json".format(task.pk))
        with report_file.open("wb") as f:
            f.write(uploaded_file.read())

        downloaded_size = report_file.stat().st_size
        if downloaded_size == expected_file_size:
            report_data = json.loads(report_file.read_text())

            log.debug("Parsing frame metrics")
            vmaf_scores = []
            psnr_scores = []
            ms_ssim_scores = []
            for frame in report_data["frames"]:
                vmaf_scores.append(frame["metrics"]["vmaf"])
                if task.psnr:
                    psnr_scores.append(frame["metrics"]["psnr_y"])
                if task.ms_ssim:
                    ms_ssim_scores.append(frame["metrics"]["float_ms_ssim"])

                # Creating Frame information
                frame = metrics.models.Frame(
                    task=task,
                    frame_number=frame["frameNum"],
                    psnr=frame["metrics"].get("psnr_y", None),
                    ms_ssim=frame["metrics"].get("float_ms_ssim", None),
                    vmaf=frame["metrics"].get("vmaf", None)
                )
                frame.save()

            log.debug("Creating pooled metrics information")
            pooled_vmaf_data = report_data["pooled_metrics"]["vmaf"]
            pooled_vmaf = metrics.models.PooledVMAF(
                task=task,
                min=pooled_vmaf_data["min"],
                one_percent_min=_get_lows(vmaf_scores),
                point_one_percent_min=_get_lows(vmaf_scores, "0.1%"),
                max=pooled_vmaf_data["max"],
                mean=pooled_vmaf_data["mean"],
                harmonic_mean=pooled_vmaf_data["harmonic_mean"]
            )
            pooled_vmaf.save()
            if task.psnr:
                pooled_psnr_data = report_data["pooled_metrics"]["psnr_y"]
                pooled_psnr = metrics.models.PooledPSNR(
                    task=task,
                    min=pooled_psnr_data["min"],
                    one_percent_min=_get_lows(psnr_scores),
                    point_one_percent_min=_get_lows(psnr_scores, "0.1%"),
                    max=pooled_psnr_data["max"],
                    mean=pooled_psnr_data["mean"],
                    harmonic_mean=pooled_psnr_data["harmonic_mean"]
                )
                pooled_psnr.save()
            if task.ms_ssim:
                pooled_ms_ssim_data = report_data["pooled_metrics"]["float_ms_ssim"]
                pooled_ms_ssim = metrics.models.PooledMSSSIM(
                    task=task,
                    min=pooled_ms_ssim_data["min"],
                    one_percent_min=_get_lows(ms_ssim_scores),
                    point_one_percent_min=_get_lows(ms_ssim_scores, "0.1%"),
                    max=pooled_ms_ssim_data["max"],
                    mean=pooled_ms_ssim_data["mean"],
                    harmonic_mean=pooled_ms_ssim_data["harmonic_mean"]
                )
                pooled_ms_ssim.save()

        else:
            log.warning(
                "Report for [{}] got wrong size file from worker: expected [{}] got [{}]".format(
                    task.pk, expected_file_size, downloaded_size
                )
            )
            report_file.unlink(missing_ok=True)

            log.debug("Re-queueing metrics calculation for task [{}]".format(task.pk))
            _queue_task(task)

        if request.headers.get("Worker", None):
            task.worker = request.headers.get("Worker")
            task.status = task.TaskStatus.COMPLETE
            task.analyze_end_datetime = timezone.now()
            task.save()

        report_file.unlink(missing_ok=True)
        log.info("Metrics task [{}] completed".format(task.pk))

        return JsonResponse(
            {"success": "metrics file uploaded successfully"},
            json_dumps_params={"indent": 2},
            status=200
        )
    elif request.method == "GET":
        return JsonResponse(
            {"success": "no data present"},
            json_dumps_params={"indent": 2},
            status=200
        )
    else:
        return JsonResponse(
            {"error": "this endpoint only supports GET/POST requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )


def api_task_source(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)

    if request.method == "GET":
        if request.headers.get("Worker", None):
            log.debug("Worker [{}] calculating metrics for [{}]".format(request.headers.get("Worker"), task.pk))
            task.worker = request.headers.get("Worker")
            task.status = task.TaskStatus.DOWNLOADING
            task.progress = 0.0
            task.processing_framerate = 0.0
            task.seconds_remaining = -1
            task.save()
        return FileResponse(open(pathlib.Path(task.source_file.directory, task.source_file.name), "rb"))
    else:
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )


def api_task_compressed(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)

    if request.method == "GET":
        if request.headers.get("Worker", None):
            log.debug("Worker [{}] calculating metrics for [{}]".format(request.headers.get("Worker"), task.pk))
            task.worker = request.headers.get("Worker")
            task.status = task.TaskStatus.DOWNLOADING
            task.analyze_start_datetime = timezone.now()
            task.save()
        return FileResponse(open(pathlib.Path(task.compressed_file.directory, task.compressed_file.name), "rb"))
    else:
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )


def api_task_worst(request, task_pk: int):
    task = get_object_or_404(metrics.models.MetricTask, pk=task_pk)

