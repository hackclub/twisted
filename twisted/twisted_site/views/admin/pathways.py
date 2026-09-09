from datetime import datetime
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ...models import Pathway, User
from .admin import AdminView


# Create your views here.
class PathwayListView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data(page="pathways")
        context["pathways"] = Pathway.objects.all().order_by("start")

        pathways = Pathway.objects.order_by("start").all()

        current_pathways: list[Pathway] = []
        past_pathways: list[Pathway] = []
        future_pathways: list[Pathway] = []

        for pathway in pathways:
            if pathway.in_progress():
                current_pathways.append(pathway)
            if pathway.ended():
                past_pathways.append(pathway)
            if pathway.didnt_start():
                future_pathways.append(pathway)

        past_pathways.reverse()
        context["current_pathways"] = current_pathways
        context["past_pathways"] = past_pathways
        context["future_pathways"] = future_pathways

        return render(request, "admin/pathways/list.html", context=context)


class PathwayCreateView(AdminView):
    def get(
        self,
        request: HttpRequest,
        error: str | None = None,
        extracontext: dict[str, Any] | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if extracontext is None:
            extracontext = {}

        context = self.get_context_data(page="pathways", subpage="create")
        context.update(extracontext)

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/create.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        pathway_name: str | None = request.POST.get("name")

        start_date: str | None = request.POST.get("startDate")
        start_time: str | None = request.POST.get("startTime")

        end_date: str | None = request.POST.get("endDate")
        end_time: str | None = request.POST.get("endTime")

        min_mins = int(request.POST.get("mins", "0"))

        errcontext: dict[str, Any] = {  # pyrefly: ignore[explicit-any]
            "pathway_name": pathway_name,
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "end_time": end_time,
            "min_mins": min_mins,
        }

        if pathway_name in (None, ""):
            return self.get(request, "No pathway name typed!", errcontext)

        if start_date in (None, ""):
            return self.get(request, "No start date selected!", errcontext)

        if start_time in (None, ""):
            return self.get(request, "No start time selected!", errcontext)

        if end_date in (None, ""):
            return self.get(request, "No end date selected!", errcontext)

        if end_time in (None, ""):
            return self.get(request, "No end time selected!", errcontext)

        if min_mins <= 0:
            return self.get(
                request, "Minimum minutes must be greater than zero!", errcontext
            )

        current_tz_offset = datetime.now(timezone.get_current_timezone()).strftime("%z")

        start = datetime.strptime(
            f"{start_date} {start_time} {current_tz_offset}", "%Y-%m-%d %H:%M %z"
        )

        end = datetime.strptime(
            f"{end_date} {end_time} {current_tz_offset}", "%Y-%m-%d %H:%M %z"
        )

        _ = Pathway.objects.create(
            start=start, end=end, name=pathway_name, min_mins=min_mins
        )

        messages.success(request, f'Successfully created Pathway for "{pathway_name}"!')

        return redirect("admin.pathways")


class PathwayDetailView(AdminView):
    def get(self, request: HttpRequest, id: int) -> HttpResponse:
        context = self.get_context_data(page="pathways", subpage="detail")
        pathway = get_object_or_404(Pathway, id=id)
        context["pathway"] = pathway

        assert isinstance(self.audit_log.additional_context, dict)
        self.audit_log.additional_context["pathway_name"] = pathway.name

        mins_per_participant = pathway.mins_spent_per_participant()
        users = User.objects.filter(id__in=mins_per_participant.keys()).select_related(
            "profile"
        )

        participants: list[dict[str, Any]] = [  # pyrefly: ignore[explicit-any]
            {
                "user": user,
                "mins": mins_per_participant[user.id],  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                "percent": min(
                    100,
                    round(mins_per_participant[user.id] / pathway.min_mins * 100),  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                )
                if pathway.min_mins != 0
                else 0,
                "qualified": mins_per_participant[user.id] >= pathway.min_mins,  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
            }
            for user in users
        ]
        participants.sort(key=lambda p: p["mins"], reverse=True)  # pyrefly: ignore[implicit-any-lambda]

        context["participants"] = participants
        context["qualified_count"] = sum(1 for p in participants if p["qualified"])

        return render(request, "admin/pathways/detail.html", context=context)
