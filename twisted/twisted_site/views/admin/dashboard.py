from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone

from twisted_site.models import (
    PROJECT_TYPE_CHOICES,
    Journal,
    Profile,
    latest_ship_status,
    status_is_shipped,
)
from twisted_site.tasks import refresh_profile_countries

from .admin import AdminView

#: Most stale countries one dashboard load queues for a refresh, so a single visit cannot
#: set off a flood of HCA requests.
COUNTRY_REFRESH_BATCH = 50
#: How long a queued refresh may take before another dashboard load is allowed to retry it.
COUNTRY_REFRESH_CLAIM = timedelta(minutes=10)


def queue_stale_country_refreshes() -> list[int]:
    """
    Queue a background HCA lookup for journal authors whose cached country has expired.

    The dashboard never calls HCA itself: it charts the cached `Profile.country` and
    lets this refresh catch it up. Queued profiles are "claimed" by pushing their cache
    expiry forward a little, so reloading the dashboard does not queue them again.
    """
    now = timezone.now()
    stale_ids = list(
        Profile.objects.filter(user__projects__journals__isnull=False)
        .filter(Q(country_cached_until__isnull=True) | Q(country_cached_until__lte=now))
        .values_list("id", flat=True)
        .distinct()[:COUNTRY_REFRESH_BATCH],
    )
    if len(stale_ids) == 0:
        return []

    _ = Profile.objects.filter(id__in=stale_ids).update(
        country_cached_until=now + COUNTRY_REFRESH_CLAIM,
    )
    transaction.on_commit(lambda: refresh_profile_countries.enqueue(stale_ids))
    return stale_ids


# Create your views here.
class DashboardView(AdminView):
    allowed = True
    page = "dashboard"

    def get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data()

        hours_logged = 0.0
        hours_logged_chart: dict[str, float] = {}
        logged_project_type: dict[str, float] = {"Software": 0, "Hardware": 0}
        shipped_project_type: dict[str, float] = {"Software": 0, "Hardware": 0}
        logged_region_hours: dict[str, float] = {}

        hours_shipped = 0.0
        hours_shipped_chart: dict[str, float] = {}

        # One grouped query instead of several queries (and an HCA call) per journal.
        rows = (
            Journal.objects.annotate(
                day=TruncDate("created_at"),
                ship_status=latest_ship_status("project"),
            )
            .values("day", "project__project_type", "project__user__profile__country", "ship_status")
            .annotate(minutes=Sum("reduced_minutes"))
            .order_by("day")
        )
        for row in rows:
            hours = (row["minutes"] or 0) / 60
            hours_logged += hours

            date = row["day"].isoformat()
            hours_logged_chart[date] = hours_logged_chart.get(date, 0) + hours

            project_type = row["project__project_type"]
            project_type_label = PROJECT_TYPE_CHOICES.get(project_type, project_type)
            logged_project_type[project_type_label] = (
                logged_project_type.get(project_type_label, 0) + hours
            )

            country = row["project__user__profile__country"] or "Unknown"
            logged_region_hours[country] = logged_region_hours.get(country, 0) + hours

            if status_is_shipped(row["ship_status"]):
                hours_shipped += hours
                hours_shipped_chart[date] = hours_shipped_chart.get(date, 0) + hours
                shipped_project_type[project_type_label] = (
                    shipped_project_type.get(project_type_label, 0) + hours
                )

        _ = queue_stale_country_refreshes()

        context["hours_logged"] = round(hours_logged, 2)
        # Rendered with json_script in the template (escapes </script> etc.).
        context["hours_logged_chart"] = [["Date", "Hours"], *list(hours_logged_chart.items())]
        context["logged_project_type"] = [["Type", "Hours"], *list(logged_project_type.items())]
        context["logged_region_hours"] = [["Country", "Hours"], *list(logged_region_hours.items())]

        context["hours_shipped"] = round(hours_shipped, 2)
        context["hours_shipped_chart"] = [["Date", "Hours"], *list(hours_shipped_chart.items())]
        context["shipped_project_type"] = [["Type", "Hours"], *list(shipped_project_type.items())]

        return TemplateResponse(request, "admin/dashboard.html", context=context)
