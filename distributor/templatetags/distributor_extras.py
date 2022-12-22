import datetime
import zoneinfo

from django import template
from django.conf import settings


register = template.Library()


@register.filter
def datetime_duration(start: datetime.datetime, end: datetime.datetime) -> str:
    return str(end - start).split(".")[0]


@register.filter
def seconds_to_duration(seconds: int) -> str:
    # Formatting as XX:YY:ZZ, it currently normally returns X:YY:ZZ, so just add a 0 if necessary.
    # And if it's over a day long (WHY), figure out how many days it is and get it looking "nice"
    delta = str(datetime.timedelta(seconds=round(seconds)))
    if seconds >= 86400:
        days = delta.split(", ")[0].split(" ")[0]
        hours, minutes, seconds = delta.split(", ")[1].split(":")
        hours = int(hours) + int(days) * 24
        return "{:2}:{:2}:{:2}".format(str(hours), str(minutes), str(seconds))
    else:
        delta_split = [x.zfill(2) for x in delta.split(":")]
        return "{:2}:{:2}:{:2}".format(delta_split[0], delta_split[1], delta_split[2])


@register.filter
def datetime_convert(dt: datetime.datetime) -> str:
    local_tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
    return dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC")).astimezone(local_tz).strftime("%Y/%m/%d %R")


@register.filter
def profile_id_rename(profile_name: str) -> str:
    return profile_name.replace(".", "").replace(" ", "_").replace("(", "").replace(")", "")


@register.simple_tag
def conversion_rate(file_duration: int, start_time: datetime.datetime, end_time: datetime.datetime) -> float:
    return round(float(file_duration) / float((end_time - start_time).seconds), 2)
