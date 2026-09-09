import zoneinfo
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils import timezone


class TimezoneMiddleware:
    get_response: Callable[[HttpRequest], HttpResponse]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            # get django_timezone from cookie
            tzname = request.COOKIES.get("django_timezone")
            if tzname not in (None, ""):
                timezone.activate(zoneinfo.ZoneInfo(tzname))
            else:
                timezone.deactivate()
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            timezone.deactivate()

        return self.get_response(request)
