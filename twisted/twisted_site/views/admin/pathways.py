from datetime import datetime
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from twisted_site.models import Pathway, PathwayGroup, User

from .admin import AdminView


# Create your views here.
class PathwayListView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")


        context = self.get_context_data(page="pathways")
        context["pathways"] = Pathway.objects.all().order_by("group__start")

        pathways = Pathway.objects.order_by("group__start").all()

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


class PathwayGroupListView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="pathways", subpage="groups")
        context["groups"] = PathwayGroup.objects.order_by("-start").prefetch_related("pathways")

        return render(request, "admin/pathways/groups/list.html", context=context)


class PathwayGroupCreateView(AdminView):
    def get(
        self,
        request: HttpRequest,
        error: str | None = None,
        extracontext: dict[str, Any] | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        if extracontext is None:
            extracontext = {}

        context = self.get_context_data(page="pathways", subpage="groups.create")
        context.update(extracontext)

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/groups/create.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        group_name: str | None = request.POST.get("name")

        start_date: str | None = request.POST.get("startDate")
        start_time: str | None = request.POST.get("startTime")

        end_date: str | None = request.POST.get("endDate")
        end_time: str | None = request.POST.get("endTime")

        errcontext: dict[str, Any] = {  # pyrefly: ignore[explicit-any]
            "group_name": group_name,
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "end_time": end_time,
        }

        if group_name in (None, ""):
            return self.get(request, "No group name typed!", errcontext)

        if start_date in (None, ""):
            return self.get(request, "No start date selected!", errcontext)

        if start_time in (None, ""):
            return self.get(request, "No start time selected!", errcontext)

        if end_date in (None, ""):
            return self.get(request, "No end date selected!", errcontext)

        if end_time in (None, ""):
            return self.get(request, "No end time selected!", errcontext)

        current_tz_offset = datetime.now(timezone.get_current_timezone()).strftime("%z")

        start = datetime.strptime(
            f"{start_date} {start_time} {current_tz_offset}",
            "%Y-%m-%d %H:%M %z",
        )

        end = datetime.strptime(f"{end_date} {end_time} {current_tz_offset}", "%Y-%m-%d %H:%M %z")

        if start >= end:
            return self.get(request, "Start must be before end!", errcontext)

        if PathwayGroup.objects.filter(start__lt=end, end__gt=start).exists():
            return self.get(request, "This time window overlaps with an existing pathway group!", errcontext)

        group = PathwayGroup.objects.create(name=group_name, start=start, end=end)

        messages.success(request, f'Successfully created pathway group "{group_name}"!')

        return redirect("admin.pathway_groups.detail", group_id=group.id)  # pyright: ignore[reportAttributeAccessIssue]


class PathwayGroupDetailView(AdminView):
    def get(
        self,
        request: HttpRequest,
        group_id: int,
        error: str | None = None,
        extracontext: dict[str, Any] | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        group = get_object_or_404(PathwayGroup, id=group_id)

        if extracontext is None:
            local_start = timezone.localtime(group.start)
            local_end = timezone.localtime(group.end)
            extracontext = {
                "group_name": group.name,
                "start_date": local_start.strftime("%Y-%m-%d"),
                "start_time": local_start.strftime("%H:%M"),
                "end_date": local_end.strftime("%Y-%m-%d"),
                "end_time": local_end.strftime("%H:%M"),
            }

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["pathway_group_name"] = group.name

        context = self.get_context_data(page="pathways", subpage="groups.detail")
        context["group"] = group
        context["pathways"] = group.pathways.order_by("name")  # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        context.update(extracontext)

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/groups/detail.html", context=context)

    def post(self, request: HttpRequest, group_id: int) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        group = get_object_or_404(PathwayGroup, id=group_id)

        group_name: str | None = request.POST.get("name")

        start_date: str | None = request.POST.get("startDate")
        start_time: str | None = request.POST.get("startTime")

        end_date: str | None = request.POST.get("endDate")
        end_time: str | None = request.POST.get("endTime")

        errcontext: dict[str, Any] = {  # pyrefly: ignore[explicit-any]
            "group_name": group_name,
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "end_time": end_time,
        }

        if group_name in (None, ""):
            return self.get(request, group_id, "No group name typed!", errcontext)

        if start_date in (None, ""):
            return self.get(request, group_id, "No start date selected!", errcontext)

        if start_time in (None, ""):
            return self.get(request, group_id, "No start time selected!", errcontext)

        if end_date in (None, ""):
            return self.get(request, group_id, "No end date selected!", errcontext)

        if end_time in (None, ""):
            return self.get(request, group_id, "No end time selected!", errcontext)

        current_tz_offset = datetime.now(timezone.get_current_timezone()).strftime("%z")

        start = datetime.strptime(
            f"{start_date} {start_time} {current_tz_offset}",
            "%Y-%m-%d %H:%M %z",
        )

        end = datetime.strptime(f"{end_date} {end_time} {current_tz_offset}", "%Y-%m-%d %H:%M %z")

        if start >= end:
            return self.get(request, group_id, "Start must be before end!", errcontext)

        if PathwayGroup.objects.filter(start__lt=end, end__gt=start).exclude(id=group_id).exists():
            return self.get(
                request,
                group_id,
                "This time window overlaps with an existing pathway group!",
                errcontext,
            )

        group.name = group_name
        group.start = start
        group.end = end
        group.save()

        messages.success(request, f'Successfully updated pathway group "{group_name}"!')

        return redirect("admin.pathway_groups.detail", group_id=group_id)


class PathwayCreateView(AdminView):
    def get(
        self,
        request: HttpRequest,
        error: str | None = None,
        extracontext: dict[str, Any] | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        if extracontext is None:
            extracontext = {}

        context = self.get_context_data(page="pathways", subpage="create")
        context["groups"] = PathwayGroup.objects.order_by("-start")
        context.update(extracontext)

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/create.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        pathway_name: str | None = request.POST.get("name")
        group_id: str | None = request.POST.get("group")
        min_mins = int(request.POST.get("mins", "0"))

        errcontext: dict[str, Any] = {  # pyrefly: ignore[explicit-any]
            "pathway_name": pathway_name,
            "group_id": group_id,
            "min_mins": min_mins,
        }

        if pathway_name in (None, ""):
            return self.get(request, "No pathway name typed!", errcontext)

        if group_id in (None, ""):
            return self.get(request, "No pathway group selected!", errcontext)

        group = PathwayGroup.objects.filter(id=group_id).first()
        if group is None:
            return self.get(request, "Selected pathway group does not exist!", errcontext)

        if min_mins <= 0:
            return self.get(request, "Minimum minutes must be greater than zero!", errcontext)

        _ = Pathway.objects.create(group=group, name=pathway_name, min_mins=min_mins)

        messages.success(request, f'Successfully created Pathway for "{pathway_name}"!')

        return redirect("admin.pathways")


class PathwayDetailView(AdminView):
    def get(self, request: HttpRequest, pathway_id: int) -> HttpResponse:
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="pathways", subpage="detail")
        pathway = get_object_or_404(Pathway, id=pathway_id)
        context["pathway"] = pathway

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["pathway_name"] = pathway.name

        mins_per_participant = pathway.mins_spent_per_participant()
        users = User.objects.filter(id__in=mins_per_participant.keys()).select_related("profile")

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
