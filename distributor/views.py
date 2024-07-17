import pathlib

from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt

import distributor.models
import distributor.serializers


########################################################################################################################
# Global Values
########################################################################################################################
ITEMS_PER_PAGE = 50


########################################################################################################################
# User Views
########################################################################################################################
def index(request):
    if request.method != "GET":
        return HttpResponse("This page only supports GET requests", status=405)
    return render(request, "distributor/management.html")


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
def api_file(request, file_id: int):
    if request.method != "GET":
        return JsonResponse(
            {"error": "this endpoint only supports GET requests, not [{}]".format(request.method)},
            json_dumps_params={"indent": 2},
            status=405
        )

    file = get_object_or_404(distributor.models.File, pk=file_id)

    return FileResponse(open(pathlib.Path(file.directory, file.name), "rb"))
