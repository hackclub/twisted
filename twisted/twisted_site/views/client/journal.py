import math
import re

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from twisted_site.models import Journal, Project, TemplateContext

HACKATIME_MAX_LOGGABLE_MINUTES = 6 * 60
IMAGE_REGEX = r"!\[([^\]]*)\]\([^)]+\)"


class NewProjectHackatimeJournal(View):
    def get(
        self,
        request: HttpRequest,
        project_id: int,
        info: str | None = None,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = TemplateContext()

        context["info"] = info
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        context["project"] = project

        if project.is_shipped():
            return redirect("fr.projects.detail", project_id)

        log_minutes = project.hackatime_time_unjournaled()

        log_minutes = min(log_minutes, HACKATIME_MAX_LOGGABLE_MINUTES)

        context["log_minutes"] = log_minutes

        return render(request, "client/projects/journal/new_hackatime.html", context=context)

    def post(self, request: HttpRequest, project_id: int) -> HttpResponse:
        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        reduced_minutes = min(project.hackatime_time_unjournaled(), HACKATIME_MAX_LOGGABLE_MINUTES)

        if project.is_shipped():
            return redirect("fr.projects.detail", project_id)

        content = request.POST["content"]

        image_count = len(re.findall(IMAGE_REGEX, content))
        required_image_count = math.ceil(max(1, reduced_minutes / 180))

        content_no_images = re.sub(IMAGE_REGEX, "", content)
        content_length = len(" ".join(content_no_images.split()))

        if image_count < required_image_count:
            return self.get(
                request,
                project_id,
                info=f"please add atleast {required_image_count - image_count} more image(s) to log this journal!",
                context={"content": content},
            )
        required_content_length = reduced_minutes // 3
        if content_length < min(100, required_content_length):
            return self.get(
                request,
                project_id,
                info=f"Content length must be more than 20 characters per hour!<br>({content_length} of {required_content_length} required)",
                context={"content": content},
            )

        journal = Journal(
            project=project,
            type="hackatime",
            content=content,
            minutes_worked=project.hackatime_time_unjournaled(),
            reduced_minutes=reduced_minutes,
        )
        journal.save()

        return self.get(request, project_id, context={"success": True})


UNTRACKED_MAX_LOGGABLE_MINUTES = 60


class NewProjectUntrackedJournal(View):
    def get(
        self,
        request: HttpRequest,
        project_id: int,
        info: str | None = None,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = TemplateContext()

        context["info"] = info
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)

        if project.user != request.user:
            return redirect("dashboard")

        if project.project_type == "software":
            return redirect("fr.projects.journals.new.hackatime")

        context["project"] = project

        log_minutes = project.hackatime_time_unjournaled()

        log_minutes = min(log_minutes, HACKATIME_MAX_LOGGABLE_MINUTES)

        context["log_minutes"] = log_minutes

        context["max_mins"] = UNTRACKED_MAX_LOGGABLE_MINUTES

        context["info"] = (
            "logging untracked journals may lead to heavy time deflation. for hardware projects, consider using lapse and sync to hackatime."
        )

        return render(request, "client/projects/journal/new_untracked.html", context=context)

    def post(self, request: HttpRequest, project_id: int) -> HttpResponse:
        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.project_type == "software":
            return redirect("fr.projects.journals.new.hackatime")

        content = request.POST["content"]
        time_logged = int(request.POST["time_logged"])

        content_no_images = re.sub(IMAGE_REGEX, "", content)
        content_length = len(" ".join(content_no_images.split()))

        if time_logged > UNTRACKED_MAX_LOGGABLE_MINUTES:
            return self.get(
                request,
                project_id,
                info=f"Time logged cannot be more than {UNTRACKED_MAX_LOGGABLE_MINUTES} minutes!",
                context={"content": content},
            )

        if time_logged < 0:
            return self.get(
                request,
                project_id,
                info="I dont understand, why do you wanna lose time :hs:",
                context={"content": content},
            )

        if content_length < min(100, time_logged * 2):
            return self.get(
                request,
                project_id,
                info=f"Content length must be more than 120 characters per hour!<br>({len(content)} of {time_logged} required)",
                context={"content": content},
            )

        journal = Journal(
            project=project,
            type="untracked",
            content=content,
            minutes_worked=time_logged,
            reduced_minutes=time_logged,
        )
        journal.save()

        return self.get(request, project_id, context={"success": True})


class DeleteJournal(View):
    def get(
        self,
        request: HttpRequest,
        journal_id: int | None,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = {"success": False}

        if request.user.is_anonymous:
            return redirect("homepage")

        if journal_id is not None:
            journal = get_object_or_404(Journal, id=journal_id)
            if journal.project.is_shipped():
                return redirect("fr.projects.detail", journal.project.id)

            if journal.project.user != request.user:
                return redirect("dashboard")

            if journal.type != "untracked":
                return redirect("dashboard")

            context["journal"] = journal

        return render(request, "client/projects/journal/delete.html", context=context)

    def post(self, request: HttpRequest, journal_id: int) -> HttpResponse:
        if request.user.is_anonymous:
            return redirect("homepage")

        journal = get_object_or_404(Journal, id=journal_id)

        if journal.project.is_shipped():
            return redirect("fr.projects.detail", journal.project.id)

        if journal.project.user != request.user:
            return redirect("dashboard")

        if journal.type != "untracked":
            return redirect("dashboard")

        _ = journal.delete()

        return self.get(request, journal_id=None, context={"success": True})
