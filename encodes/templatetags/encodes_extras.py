import datetime
import zoneinfo

from django import template
from django.conf import settings


register = template.Library()


@register.filter
def datetime_duration(start: datetime.datetime, end: datetime.datetime) -> str:
    return str(end - start).split(".")[0]


@register.filter
def datetime_convert(dt: datetime.datetime) -> str:
    local_tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
    return dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC")).astimezone(local_tz).strftime("%Y/%m/%d %R")


@register.filter
def profile_id_rename(profile_name: str) -> str:
    return profile_name.replace(".", "").replace(" ", "_").replace("(", "").replace(")", "")


@register.simple_tag
def conversion_rate(file_duration: int, start_time: datetime.datetime, end_time: datetime.datetime) -> str:
    return str(round(float(file_duration) / float((end_time - start_time).seconds), 2))
