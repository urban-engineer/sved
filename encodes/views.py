import concurrent.futures
import json
import pathlib

import django.core.handlers.wsgi
from django.db.models import Avg, Count, Q
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import distributor.models
import distributor.serializers
import distributor.utilities

import encodes.models
import encodes.serializers

from utils import config
from utils import ffprobe
from utils import log
from utils import mkvtoolnix
from utils import rabbit_handler


########################################################################################################################
# Helpers
########################################################################################################################
def _queue_task(task: encodes.models.EncodeTask, is_secure: bool = False) -> None:
    """
    Queue a task.  Creates and sends message to rabbitmq for processing by workers, then sets
    the task's status to Queued.

    :param task: task to queue
    :param is_secure: whether we're using https or not
    :return: None
    """
    message_data = {
        "type": "encode",
        "id": task.id,
        "url": task.get_encode_task_url(is_secure=is_secure)
    }

    log.info("Queuing Encode Task [{}] - [{}]".format(task.pk, task.source_file.name))
    rabbit_handler.send_message(message_data)

    task.status = task.TaskStatus.QUEUED
    task.save()


########################################################################################################################
# User Views
########################################################################################################################
def index(request):
    # TODO: Mark files that don't exist at time of scan
    import_directory = config.load_input_directory()
    output_directory = config.load_output_directory()

    if request.method == "GET":
        log.info("Checking for pending files to encode")

        # Get all files in the import directory, some of which may or may not be encoded or queued to encode.
        import_files = [x for x in import_directory.iterdir() if x.is_file() and x.name.endswith("mkv")]

        # Get all completed files in the output directory (which may not be in the DB)
        output_files = [x for x in output_directory.rglob("*.mkv")]

        # Get list of incomplete Jobs
        query = ~Q(status=encodes.models.EncodeTask.TaskStatus.COMPLETE)
        pending_task_files = [x.source_file.name for x in encodes.models.EncodeTask.objects.filter(query)]
        log.debug("Found [{}] queued encode tasks in DB".format(len(pending_task_files)))

        # Check if any pending jobs have the same file name as the scanned files
        # If so, don't show them to the user.  If not, then show them to the user so they can scan
        # We also ignore any files with the same name in the output directory, assuming they are the result
        # of an earlier encode task.
        files_to_scan = []
        for file in import_files:
            if file.name not in pending_task_files and file.name not in [x.name for x in output_files]:
                files_to_scan.append(file)

        log.debug("Scanning [{}] files not already queued".format(len(files_to_scan)))

        files_information = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_file = {executor.submit(distributor.utilities.create_file, x): x for x in files_to_scan}
            for future in concurrent.futures.as_completed(future_to_file):
                file_object = future.result()
                if file_object:
                    files_information.append(file_object)

        files_information = sorted(files_information, key=lambda k: k.name)

        context = {
            "files": files_information,
            "profiles": encodes.models.Profile.objects.all()
        }
        return render(request, "encodes/management.html", context)
    else:
        return HttpResponse("This page only supports GET requests", status=405)


def ingest(request):
    import_directory = config.load_input_directory()
    output_directory = config.load_output_directory()

    if request.method == "POST":
        if not request.POST.get("profile"):
            return HttpResponse("Missing profile response", status=400)
        profile = encodes.models.Profile.objects.filter(pk=request.POST.get("profile")).first()

        for file in request.POST.getlist("files_to_scan"):
            log.debug("Scanning [{}]".format(file))

            full_file_path = pathlib.Path(import_directory, file)
            source_file = distributor.utilities.create_file(full_file_path)

            compressed_file, created = distributor.models.File.objects.get_or_create(
                name=file,
                directory=str(output_directory.joinpath(profile.name)),
            )

            task = encodes.models.EncodeTask.objects.create(
                source_file=source_file,
                compressed_file=compressed_file,
                profile=profile,
                encode_type=profile.encode_type,
                encode_value=profile.encode_value
            )
            _queue_task(task)

        return HttpResponseRedirect(reverse("encodes:incomplete-tasks"))
    else:
        return HttpResponse("This page only supports POST requests", status=405)


def completed_tasks(request):
    # TODO: benchmark current implementation vs. task query per profile
    relevant_tasks = encodes.models.EncodeTask.objects.filter(status=encodes.models.EncodeTask.TaskStatus.COMPLETE)
    all_profiles = encodes.models.Profile.objects.all()
    tasks_by_profile = {x.name: {} for x in all_profiles}

    for profile in all_profiles:
        profile_information: dict = {
            "id": profile.pk,
            "jobs": [x for x in relevant_tasks if x.profile.pk == profile.pk],
        }

        if len(profile_information["jobs"]) > 0:
            encode_rates = [x.encode_framerate for x in profile_information.get("jobs", [])]
            profile_information["stats"] = {
                "average_fps": round(sum(encode_rates) / len(profile_information["jobs"]), 2),
                "completed_jobs": len(profile_information["jobs"]),
            }

        tasks_by_profile[profile.name] = profile_information

    context = {
        "jobs_complete": tasks_by_profile,
        "profile_tables": " ".join(["table_{}".format(x.id) for x in all_profiles])
    }
    return render(request, "encodes/encodes/completed.html", context)


def incomplete_tasks(request):
    queued_statuses = [
        encodes.models.EncodeTask.TaskStatus.CREATED,
        encodes.models.EncodeTask.TaskStatus.QUEUED
    ]
    in_progress_statuses = [
        encodes.models.EncodeTask.TaskStatus.DOWNLOADING,
        encodes.models.EncodeTask.TaskStatus.IN_PROGRESS,
        encodes.models.EncodeTask.TaskStatus.UPLOADING
    ]

    # We create the `job_status_list` object as an easy way to get the display string for each enum
    # in a simple way.  I'm not married to this, but it gets the job done.
    context = {
        "jobs_queued": encodes.models.EncodeTask.objects.filter(status__in=queued_statuses),
        "jobs_in_progress": encodes.models.EncodeTask.objects.filter(status__in=in_progress_statuses),
        "job_status": encodes.models.EncodeTask.TaskStatus,
        "job_status_list": json.dumps([x.label for x in encodes.models.EncodeTask.TaskStatus])
    }
    return render(request, "encodes/encodes/incomplete.html", context)


def profiles(request):
    context = {
        "profiles": encodes.models.Profile.objects.all()
    }
    return render(request, "encodes/profiles.html", context)


def worker_stats(request):
    # NOTE: This was just for figuring out the encode rate of each worker.
    # However, I think this would be useful as a stats page in the future.
    # See how each worker performs, how many jobs they've completed, etc.
    # For now, it's left here as a way to show aggregation and selection.

    # TODO: Figure out a way to get the DB to spit this out.
    relevant_jobs = encodes.models.EncodeTask.objects.filter(status=encodes.models.EncodeTask.TaskStatus.COMPLETE)
    workers = [x["worker"] for x in relevant_jobs.values("worker").annotate(Count("id")).order_by()]
    fps_by_worker = {}

    for worker in workers:
        worker_jobs = relevant_jobs.filter(worker=worker)
        fps_by_worker[worker] = float(worker_jobs.aggregate(Avg("encode_fps"))["encode_fps__avg"])

    log.debug(fps_by_worker)

    context = {
        "profiles": encodes.models.Profile.objects.all()
    }
    return render(request, "encodes/profiles.html", context)


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

    tasks = encodes.models.EncodeTask.objects.all()
    serializer = encodes.serializers.EncodeTaskSerializer(tasks, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


def api_tasks_in_progress(request):
    tasks = encodes.models.EncodeTask.objects.all().exclude(status=encodes.models.EncodeTask.TaskStatus.COMPLETE)
    serializer = encodes.serializers.EncodeTaskSerializer(tasks, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


@csrf_exempt
def api_task_detail(request, task_pk: int):
    # GET to get the JSON information
    # POST to update task
    task = get_object_or_404(encodes.models.EncodeTask, pk=task_pk)

    if request.method == "POST":
        progress_data = json.loads(request.body)
        worker = request.headers.get("Worker", None)

        if "progress" not in progress_data.keys():
            log.warning("Received POST to task detail view missing [progress] key")
            return JsonResponse({"error": "Missing data key [progress]"}, json_dumps_params={"indent": 2}, status=400)
        task.progress = progress_data.get("progress", 0)

        # FPS and ETA are optional, since for the first 5s of processing they're wildly inaccurate
        task.encode_framerate = progress_data.get("fps", 0.0)
        task.seconds_remaining = progress_data.get("eta", -1)

        # Encode type & value are optional too, and should only be sent at the start of an encode
        # (or a re-encode if the first encode fails to pass scene rules)
        task.encode_type = progress_data.get("encode_type", task.encode_type)
        task.encode_value = progress_data.get("encode_value", task.encode_value)

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
        serializer = encodes.serializers.EncodeTaskSerializer(task)
        return_data = serializer.data.copy()
        return JsonResponse(return_data, safe=False, json_dumps_params={"indent": 2})

    return JsonResponse(
        {"error": "this endpoint only supports GET/POST requests, not [{}]".format(request.method)},
        json_dumps_params={"indent": 2},
        status=405
    )


@csrf_exempt
def api_task_file(request, task_pk: int):
    # GET to download source file
    # POST to upload compressed file
    task = get_object_or_404(encodes.models.EncodeTask, pk=task_pk)

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

        source_file = task.source_file
        compressed_file = task.compressed_file

        log.debug(
            "Saving encode of [{}] to [{}]".format(
                source_file.name,
                compressed_file.get_full_path().relative_to(config.load_output_directory())
            )
        )
        compressed_file.get_full_path().parent.mkdir(exist_ok=True, parents=True)
        task.status = task.TaskStatus.UPLOADING
        task.save()

        with compressed_file.get_full_path().open("wb") as f:
            f.write(uploaded_file.read())

        downloaded_size = compressed_file.get_full_path().stat().st_size
        if downloaded_size == expected_file_size:
            log.debug("Updating file [{}] database entry".format(compressed_file.id))
            file_information = ffprobe.get_file_info(compressed_file.get_full_path())

            compressed_file.size = int(file_information.format.get("size", -1))
            compressed_file.duration = file_information.duration
            compressed_file.frame_rate = round(eval(file_information.video_stream["avg_frame_rate"]), 3)
            compressed_file.frames = file_information.frames
            compressed_file.ffprobe_information = json.loads(str(file_information))
            compressed_file.save()
        else:
            log.warning(
                "Encode [{}] got wrong size file from worker: expected [{}] got [{}]".format(
                    task.id, expected_file_size, downloaded_size
                )
            )

            invalid_directory = config.load_output_directory().joinpath("invalid", task.profile.name)
            log.debug("Moving output to [{}]".format(invalid_directory.joinpath(compressed_file.name)))

            invalid_directory.mkdir(parents=True, exist_ok=True)
            compressed_file.get_full_path().rename(invalid_directory.joinpath(compressed_file.name))

            log.debug("Re-queueing message")
            _queue_task(task)

        if request.headers.get("Worker", None):
            task.worker = request.headers.get("Worker")
            task.status = task.TaskStatus.COMPLETE
            task.encode_end_datetime = timezone.now()
            task.save()

        if config.load_flags()["auto-delete"]:
            source_file.get_full_path().unlink(missing_ok=False)

        log.info("Encode task [{}] completed".format(task.pk))

        return JsonResponse(
            {"success": "file uploaded successfully"},
            json_dumps_params={"indent": 2},
            status=200
        )

    elif request.method == "GET":
        if request.headers.get("Worker", None):
            log.debug("Worker [{}] processing encode [{}]".format(request.headers.get("Worker"), task.pk))
            task.worker = request.headers.get("Worker")
            task.status = task.TaskStatus.DOWNLOADING
            task.progress = 0.0
            task.encode_framerate = 0.0
            task.seconds_remaining = -1
            task.encode_start_datetime = timezone.now()
            task.save()
        return FileResponse(open(pathlib.Path(task.source_file.directory, task.source_file.name), "rb"))

    return JsonResponse(
        {"error": "this endpoint only supports GET/POST requests, not [{}]".format(request.method)},
        json_dumps_params={"indent": 2},
        status=405
    )


def api_profile_list(request):
    # if request.method != "GET":
    #     return JsonResponse(
    #         {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
    #         json_dumps_params={"indent": 2},
    #         status=405
    #     )
    #
    # all_profiles = distributor.models.Profile.objects.all()
    # serializer = distributor.serializers.ProfileSerializer(all_profiles, many=True)
    # return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})
    pass


def api_profile_detail(request):
    pass


def api_profile_file_list(request):
    pass
