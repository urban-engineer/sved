import typing

import requests
import time
import typing

from utils import log


def send_get_request(url: str, **kwargs) -> requests.Response:
    """
    Send a GET request to a URL with arbitrary parameter dict kwargs, return the response with proper encoding if the
    Byte Order Mark is present.

    :param url: URL to GET
    :param kwargs: arbitrary parameters to send with the request
    :return: Response from URL, with encoding set properly if necessary.
    """

    response = requests.get(url, **kwargs)

    # Checking for the Byte Order Mark (BOM), which we need to change encoding to properly handle later on
    if response.text.startswith("\ufeff"):
        response.encoding = "utf-8-sig"

    return response


def send_post_request(url: str, **kwargs) -> requests.Response:
    """
    Send a POST request to a URL with arbitrary parameter dict kwargs, return the response with proper encoding if the
    Byte Order Mark is present.

    :param url: URL to POST
    :param kwargs: arbitrary parameters to send with the request
    :return: Response from URL, with encoding set properly if necessary.
    """

    response = requests.post(url, **kwargs)

    # Checking for the Byte Order Mark (BOM), which we need to change encoding to properly handle later on
    if response.text.startswith("\ufeff"):
        response.encoding = "utf-8-sig"

    return response
