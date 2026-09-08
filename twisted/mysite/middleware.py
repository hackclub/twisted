import zoneinfo

from django.utils import timezone


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # get django_timezone from cookie
            tzname: str | None = request.COOKIES.get("django_timezone")
            if tzname not in (None, ""):
                timezone.activate(zoneinfo.ZoneInfo(tzname))
            else:
                timezone.deactivate()
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            timezone.deactivate()

        return self.get_response(request)
