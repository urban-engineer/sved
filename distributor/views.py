import datetime
import json
import math
import pathlib
import socket
import subprocess

import time
import concurrent.futures

import django.core.handlers.wsgi
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import distributor.models
import distributor.serializers

from utils import config
from utils import log
from utils import rabbit_handler
from utils import subprocess_handler


########################################################################################################################
# Global Values
########################################################################################################################
ITEMS_PER_PAGE = 50


########################################################################################################################
# Helpers
########################################################################################################################
def _get_file_url(file_id: int, is_secure: bool) -> str:
    """
    Get the URL for the actual file of a file ID

    :param file_id: file to look up
    :param is_secure: whether we're using https or not
    :return: URL serving the file itself
    """

    request_host = "{}:{}".format(socket.gethostbyname(socket.gethostname()), "8080")

    if is_secure:
        return "https://{}{}".format(request_host, reverse("distributor:api-file", args=(file_id,)))
    else:
        return "http://{}{}".format(request_host, reverse("distributor:api-file", args=(file_id,)))


def _get_file_detail_url(file_id: int, is_secure: bool) -> str:
    """
    Get the URL for the file's detail

    :param file_id: file to look up
    :param is_secure: whether we're using https or not
    :return: URL to the file's detail page
    """

    request_host = "{}:{}".format(socket.gethostbyname(socket.gethostname()), "8080")

    if is_secure:
        return "https://{}{}".format(request_host, reverse("distributor:api-file-detail", args=(file_id,)))
    else:
        return "http://{}{}".format(request_host, reverse("distributor:api-file-detail", args=(file_id,)))


def _queue_file(file: distributor.models.File, is_secure: bool) -> None:
    serializer = distributor.serializers.FileSerializer(file)
    message_data = serializer.data.copy()
    message_data["file_detail_url"] = _get_file_detail_url(file.id, is_secure)
    message_data["file_url"] = _get_file_url(file.id, is_secure)
    message_data["profile"] = json.dumps(json.loads(file.profile.definition))

    log.debug("Publishing message for [{}]".format(str(file.full_path())))
    rabbit_handler.send_message(message_data)
    file.status = "queued"
    file.save()


def _get_ffprobe_stats(file_path: pathlib.Path) -> dict:
    ffprobe_command = "ffprobe -v quiet -print_format json -show_format -show_streams \"{}\"".format(str(file_path))
    code, out, err = subprocess_handler.run_command(ffprobe_command, print_output=False)
    if code != 0:
        raise RuntimeError("ffprobe on [{}] returned code [{}]".format(file_path.name, code))

    return json.loads("\n".join([x for x in out if x]))


def _format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    s = round(size_bytes / math.pow(1024, i), 2)
    return "{}{}".format(s, size_name[i])


########################################################################################################################
# User Views
########################################################################################################################
def index(request):
    import_directory = config.load_input_directory()
    output_directory = config.load_output_directory()

    # Show a display under the "Submit" button on the index page, something like:
    #  <profile>
    #    <file 1>
    #    <file 2>
    #    ...
    #  <profile>
    #    <file 1>
    #    <file 2>
    #    ...
    #
    # Then a second submit button that submits those for auto-import
    # And then change behavior so a submit of "manual" files sends the user to the jobs page.

    if request.method == "POST":
        for file in request.POST.getlist("files_to_scan"):
            log.debug("Scanning [{}]".format(file))
            ffprobe_command = "ffprobe -v error -show_entries format=duration"
            ffprobe_command += " -of default=noprint_wrappers=1:nokey=1 \"{}\"".format(import_directory.joinpath(file))
            ffprobe_output = subprocess.run(
                ffprobe_command.format(import_directory.joinpath(file)),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )

            if not request.POST.get("profile"):
                return HttpResponse("Missing profile response", status=400)

            profile = distributor.models.Profile.objects.filter(pk=request.POST.get("profile")).first()

            # Encountered a few files where there was some extra output here delimited by new lines, so, handling that.
            # (Dunno how that happened but even re-adding statistics via mkvpropedit didn't change it)
            if len(ffprobe_output.stdout.splitlines(keepends=False)) > 1:
                duration = float(ffprobe_output.stdout.splitlines(keepends=False)[0])
            else:
                duration = float(ffprobe_output.stdout)

            # Put the file in the DB
            # TODO: Find out what happens when we add a file again after encoding it, same profile and all
            # (no issues with different profiles, but the above case would result in a "duplicate" row)
            file = distributor.models.File(
                name=file,
                path=str(import_directory),
                duration=duration,
                profile=profile,
                status="created",
                creation_datetime=timezone.now()
            )
            file.save()

            _queue_file(file, request.is_secure())

        return HttpResponseRedirect(reverse("distributor:index"))

    elif request.method == "GET":
        # Check for pending files to encode

        # Get list of files in input directory

        # TODO: scan for any arbitrary video file input
        # (apply the same logic to the output file check below)
        file_names = [x.name for x in import_directory.glob("*.mkv")]

        # Get list of incomplete Jobs
        pending_jobs = [x.name for x in distributor.models.File.objects.all() if x.status != "complete"]

        # Get all completed files in the output directory (which may not be in the DB)
        output_files = [x.name for x in output_directory.rglob("*.mkv") if x.is_file()]

        # Check if any pending jobs have the same file name as the scanned files
        # If so, don't show them to the user.  If not, then show them to the user so they can scan
        files_to_scan = []
        for file_name in file_names:
            if not any([True for x in pending_jobs if file_name == x]) and file_name not in output_files:
                files_to_scan.append(import_directory.joinpath(file_name))

        files_information = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_file = {executor.submit(_get_ffprobe_stats, x): x for x in files_to_scan}
            for future in concurrent.futures.as_completed(future_to_file):
                file_information = future.result()["format"]
                bits = int(file_information.get("size", 0)) * 8
                seconds = round(float(file_information.get("duration", 0)))

                # If file is being written to this location, ignore it
                if seconds != 0 and bits != 0:
                    files_information.append(
                        {
                            "name": future_to_file[future].name,
                            "duration": str(datetime.timedelta(seconds=seconds)),
                            "size": _format_size(bits // 8),
                            "bit_rate": _format_size(bits // seconds).replace("B", "b") + "/s"
                        }
                    )

        files_information = sorted(files_information, key=lambda k: k["name"])

        context = {
            "files": files_information,
            "profiles": distributor.models.Profile.objects.all()
        }
        return render(request, "distributor/management.html", context)
    else:
        return HttpResponse("This page only supports POST or GET requests", status=405)


def incomplete_encodes(request):
    relevant_jobs = [x for x in distributor.models.File.objects.filter(status__in=["created", "queued", "in progress"])]

    jobs_queued = [x for x in relevant_jobs if x.status.lower() in ["created", "queued"]]
    jobs_in_progress = [x for x in relevant_jobs if x.status.lower() == "in progress"]

    context = {
        "jobs_queued": jobs_queued,
        "jobs_in_progress": jobs_in_progress
    }
    return render(request, "distributor/encodes/incomplete.html", context)


def completed_encodes(request):
    relevant_jobs = [x for x in distributor.models.File.objects.filter(status__iexact="complete")]
    all_profiles = [x for x in distributor.models.Profile.objects.all()]
    jobs_by_profile = {x.name: {} for x in all_profiles}

    for profile in all_profiles:
        profile_information = {
            "id": profile.id,
            "jobs": [x for x in relevant_jobs if x.profile.name == profile.name],
        }

        if len(profile_information["jobs"]) > 0:
            profile_information["stats"] = {
                "average_fps": round(
                    sum([x.fps for x in profile_information["jobs"]]) / len(profile_information["jobs"]),
                    2
                ),
                "completed_jobs": len(profile_information["jobs"]),
            }

        jobs_by_profile[profile.name] = profile_information

    context = {
        "jobs_complete": jobs_by_profile,
        "profile_tables": " ".join(["table_{}".format(x.id) for x in all_profiles])
    }
    return render(request, "distributor/encodes/completed.html", context)


def profiles(request):
    context = {
        "profiles": distributor.models.Profile.objects.all()
    }
    return render(request, "distributor/profiles.html", context)


########################################################################################################################
# API Views
########################################################################################################################
@csrf_exempt
def api_file_list(request):
    if request.method != "GET":
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )

    files = distributor.models.File.objects.all()
    serializer = distributor.serializers.FileSerializer(files, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


@csrf_exempt
def api_file_detail(request, file_id: int):
    file = get_object_or_404(distributor.models.File, pk=file_id)
    if request.method == "POST":
        progress_data = json.loads(request.body)
        worker = request.headers.get("Worker", None)

        progress = progress_data.get("progress", None)
        if not progress:
            log.warning("Received POST to file detail view missing [progress] key")
            return JsonResponse({"error": "Missing data key [progress]"}, json_dumps_params={"indent": 2}, status=400)

        # FPS and ETA are optional, since for the first 10s or so Handbrake doesn't report either
        # (which is fine, because the first 10s are going to be wildly inaccurate)
        fps = progress_data.get("fps", 0.0)
        eta = progress_data.get("eta", -1)

        if worker and worker != file.worker:
            log.warning(
                "Worker [{}] logged as processing [{}] ({}) but [{}] is sending updates".format(
                    file.worker, file.name, file.id, worker
                )
            )
            file.worker = worker

        if file.status != "in progress":
            file.status = "in progress"

        file.progress = progress
        file.fps = fps
        file.eta = eta
        file.save()
    elif request.method == "GET":
        serializer = distributor.serializers.FileSerializer(file)

        return_data = serializer.data.copy()
        return_data["file"] = _get_file_url(file_id, request.is_secure())
        return JsonResponse(return_data, safe=False, json_dumps_params={"indent": 2})

    return JsonResponse(
        {"error": "this endpoint only supports GET/POST requests, not [{}]".format(request.method)},
        json_dumps_params={"indent": 2},
        status=405
    )


@csrf_exempt
def api_file(request, file_id: int):
    file = get_object_or_404(distributor.models.File, pk=file_id)

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
        # This is probably _really_ unsafe, error-prone, and inefficient.
        # However, it also works on my machine(s), so, it's perfect.

        uploaded_file: django.core.handlers.wsgi.LimitedStream = request.META.get("wsgi.input")
        if not uploaded_file:
            log.error("POST request from worker missing file")
            return JsonResponse(
                {"error": "no file in request"},
                json_dumps_params={"indent": 2},
                status=400
            )

        output_file = pathlib.Path(config.load_output_directory(), file.profile.name, file.name)
        log.debug("Saving encode of [{}] to [{}]".format(file.name, output_file))
        output_file.parent.mkdir(exist_ok=True, parents=True)

        with output_file.open("wb") as f:
            while uploaded_file.remaining > 0:
                f.write(uploaded_file.read(16777216))

        downloaded_size = output_file.stat().st_size
        if downloaded_size != expected_file_size:
            log.warning(
                "Downloaded file size of [{}] [{}] does not match expected size of [{}]".format(
                    file.id, downloaded_size, expected_file_size
                )
            )

            invalid_directory = config.load_output_directory().joinpath("invalid", file.profile.name)
            log.debug("Moving output to [{}]".format(invalid_directory.joinpath(file.name)))

            invalid_directory.mkdir(parents=True, exist_ok=True)
            output_file.rename(invalid_directory.joinpath(file.name))

            log.debug("Re-queueing message")
            _queue_file(file, request.is_secure())

        if request.headers.get("Worker", None):
            file.worker = request.headers.get("Worker")
            file.status = "complete"
            file.encode_end_datetime = timezone.now()
            file.save()

        if config.load_flags()["auto-delete"]:
            pathlib.Path(file.path, file.name).unlink()

        return JsonResponse(
            {"success": "file uploaded successfully"},
            json_dumps_params={"indent": 2},
            status=200
        )

    elif request.method == "GET":
        if request.headers.get("Worker", None):
            log.debug("Worker [{}] beginning processing of [{}]".format(request.headers.get("Worker"), file.name))
            file.worker = request.headers.get("Worker")
            file.status = "in progress"
            file.progress = 0.0
            file.fps = 0.0
            file.eta = -1
            file.encode_start_datetime = timezone.now()
            file.save()
        return FileResponse(open(pathlib.Path(file.path, file.name), "rb"))

    return JsonResponse(
        {"error": "this endpoint only supports GET/POST requests, not [{}]".format(request.method)},
        json_dumps_params={"indent": 2},
        status=405
    )


@csrf_exempt
def api_profile_file_list(request, profile: str):
    if request.method != "GET":
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )

    files = distributor.models.File.objects.filter(profile__name__iexact=profile)
    serializer = distributor.serializers.FileSerializer(files, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


@csrf_exempt
def api_file_in_progress(request):
    files = distributor.models.File.objects.filter(status__iexact="in progress")
    serializer = distributor.serializers.FileSerializer(files, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})


@csrf_exempt
def api_profile_list(request):
    if request.method != "GET":
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )

    all_profiles = distributor.models.Profile.objects.all()
    serializer = distributor.serializers.ProfileSerializer(all_profiles, many=True)
    return JsonResponse(serializer.data, safe=False, json_dumps_params={"indent": 2})
