from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from ...models import Pathway, User
from .admin import AdminView


# Create your views here.
class PathwayListView(AdminView):
    def get(self, request):
        context = self.get_context_data(page="pathways")
        context["pathways"] = Pathway.objects.all().order_by("start")

        pathways = Pathway.objects.order_by("start").all()

        current_pathways = []
        past_pathways = []
        future_pathways = []

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
    def get(self, request, error=None, extracontext={}):
        context = self.get_context_data(page="pathways", subpage="create")
        context.update(extracontext)

        if error:
            messages.error(request, error)

        return render(request, "admin/pathways/create.html", context=context)

    def post(self, request):
        pathway_name = request.POST.get("name")

        start_date = request.POST.get("startDate")
        start_time = request.POST.get("startTime")

        end_date = request.POST.get("endDate")
        end_time = request.POST.get("endTime")

        min_mins = int(request.POST.get("mins", "0"))

        errcontext = {
            "pathway_name": pathway_name,
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "end_time": end_time,
            "min_mins": min_mins,
        }

        if "form validation":
            if not pathway_name:
                return self.get(request, "No pathway name typed!", errcontext)

            if not start_date:
                return self.get(request, "No start date selected!", errcontext)

            if not start_time:
                return self.get(request, "No start time selected!", errcontext)

            if not end_date:
                return self.get(request, "No end date selected!", errcontext)

            if not end_time:
                return self.get(request, "No end time selected!", errcontext)

            if not min_mins:
                return self.get(
                    request, "Minimum minutes must be greater than zero!", errcontext
                )

        current_tz_offset = timezone.datetime.now(
            timezone.get_current_timezone()
        ).strftime("%z")

        start = timezone.datetime.strptime(
            f"{start_date} {start_time} {current_tz_offset}", "%Y-%m-%d %H:%M %z"
        )

        end = timezone.datetime.strptime(
            f"{end_date} {end_time} {current_tz_offset}", "%Y-%m-%d %H:%M %z"
        )

        Pathway.objects.create(
            start=start, end=end, name=pathway_name, min_mins=min_mins
        )

        messages.success(request, f'Successfully created Pathway for "{pathway_name}"!')

        return redirect("admin.pathways")


class PathwayDetailView(AdminView):
    def get(self, request, id):
        context = self.get_context_data(page="pathways", subpage="detail")
        pathway = Pathway.objects.get(id=id)
        context["pathway"] = pathway

        self.audit_log.additional_context["pathway_name"] = pathway.name

        mins_per_participant = pathway.mins_spent_per_participant()
        users = User.objects.filter(id__in=mins_per_participant.keys()).select_related(
            "profile"
        )

        participants = [
            {
                "user": user,
                "mins": mins_per_participant[user.id],
                "percent": min(
                    100, round(mins_per_participant[user.id] / pathway.min_mins * 100)
                )
                if pathway.min_mins
                else 0,
                "qualified": mins_per_participant[user.id] >= pathway.min_mins,
            }
            for user in users
        ]
        participants.sort(key=lambda p: p["mins"], reverse=True)

        context["participants"] = participants
        context["qualified_count"] = sum(1 for p in participants if p["qualified"])

        return render(request, "admin/pathways/detail.html", context=context)
