import math
import re
from logging import getLogger

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from requests import RequestException

from twisted_site.models import Journal, Project, TemplateContext
from twisted_site.slack import escape_mrkdwn, log_to_channel

logger = getLogger(__name__)

HACKATIME_MAX_LOGGABLE_MINUTES = 999 * 60
UNTRACKED_MAX_LOGGABLE_MINUTES = 60 * 3
IMAGE_REGEX = r"!\[([^\]]*)\]\([^)]+\)"

HACKATIME_UNAVAILABLE_MESSAGE = (
    "Hackatime is unavailable right now, so this journal cannot be logged. "
    "Please try again in a few minutes."
)
UNTRACKED_DEFLATION_MESSAGE = (
    "logging untracked journals may lead to heavy time deflation. "
    "for hardware projects, consider using lapse and sync to hackatime."
)


def _hackatime_unjournaled_minutes(project: Project) -> int | None:
    """Return unjournaled Hackatime minutes, or None when Hackatime cannot be reached."""
    try:
        return project.hackatime_time_unjournaled()
    except RequestException:
        logger.exception("Could not load Hackatime time for project %s", project.id)
        return None


def _prose_length(content: str) -> int:
    """Count the words in journal content, ignoring image markdown."""
    without_images = re.sub(IMAGE_REGEX, "", content)
    return len(" ".join(without_images.split()))


def _prose_requirement(required_length: int, content_length: int) -> str:
    return (
        f"Content length must be at least {required_length} characters ({content_length} written)."
    )


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

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.is_shipped():
            return redirect("fr.projects.detail", project_id)

        context["project"] = project
        context["max_minutes"] = HACKATIME_MAX_LOGGABLE_MINUTES
        context["info"] = info

        unjournaled_minutes = _hackatime_unjournaled_minutes(project)
        if unjournaled_minutes is None:
            context["log_minutes"] = 0
            context["info"] = HACKATIME_UNAVAILABLE_MESSAGE
        else:
            context["log_minutes"] = min(unjournaled_minutes, HACKATIME_MAX_LOGGABLE_MINUTES)

        return render(request, "client/projects/journal/new_hackatime.html", context=context)

    def post(self, request: HttpRequest, project_id: int) -> HttpResponse:
        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.is_shipped():
            return redirect("fr.projects.detail", project_id)

        available_minutes = _hackatime_unjournaled_minutes(project)
        if available_minutes is None:
            return self.get(request, project_id)

        if available_minutes < 0:
            return self.get(
                request,
                project_id,
                info="There is no unjournaled Hackatime time available.",
            )

        reduced_minutes = min(available_minutes, HACKATIME_MAX_LOGGABLE_MINUTES)

        content = request.POST.get("content", "")

        image_count = len(re.findall(IMAGE_REGEX, content))
        required_image_count = math.ceil(max(1, reduced_minutes / 180))

        content_length = _prose_length(content)

        if image_count < required_image_count:
            return self.get(
                request,
                project_id,
                info=f"please add atleast {required_image_count - image_count} more image(s) to log this journal!",
                context={"content": content},
            )

        required_content_length = min(100, reduced_minutes // 3)
        if content_length < required_content_length:
            return self.get(
                request,
                project_id,
                info=_prose_requirement(required_content_length, content_length),
                context={"content": content},
            )

        journal = Journal(
            project=project,
            type="hackatime",
            content=content,
            minutes_worked=available_minutes,
            reduced_minutes=reduced_minutes,
        )
        journal.save()

        log_to_channel(
            f":haiku: *New journal for {escape_mrkdwn(project.project_name)}!*\n- {journal.reduced_minutes} minutes",
        )

        return self.get(request, project_id, context={"success": True})


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

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)

        if project.user != request.user:
            return redirect("dashboard")

        if project.project_type == "software":
            return redirect("fr.projects.journals.new.hackatime", project_id=project_id)

        context["project"] = project
        context["max_mins"] = UNTRACKED_MAX_LOGGABLE_MINUTES
        context["info"] = info if info not in (None, "") else UNTRACKED_DEFLATION_MESSAGE

        return render(request, "client/projects/journal/new_untracked.html", context=context)

    def post(self, request: HttpRequest, project_id: int) -> HttpResponse:
        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.project_type == "software":
            return redirect("fr.projects.journals.new.hackatime", project_id=project_id)

        content = request.POST.get("content", "")

        try:
            time_logged = int(request.POST.get("time_logged", ""))
        except ValueError:
            return self.get(
                request,
                project_id,
                info="Time logged must be a whole number of minutes.",
                context={"content": content},
            )

        content_length = _prose_length(content)

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

        required_content_length = min(100, time_logged * 2)
        if content_length < required_content_length:
            return self.get(
                request,
                project_id,
                info=_prose_requirement(required_content_length, content_length),
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


class EditJournal(View):
    def get(
        self,
        request: HttpRequest,
        id: int,
        info: str | None = None,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        journal = get_object_or_404(Journal, id=id)
        if journal.project.is_shipped():
            return redirect("fr.projects.detail", project_id=journal.project.id)
        if journal.project.user != request.user:
            return redirect("fr.projects.detail", journal.project.id)
        if context is None:
            context = TemplateContext()
        if info is not None:
            context["info"] = info
        context["journal"] = journal
        return render(request, "client/projects/journal/edit.html", context)

    def post(self, request: HttpRequest, id: int) -> HttpResponse:
        journal = get_object_or_404(Journal, id=id)

        if journal.project.is_shipped():
            return redirect("fr.projects.detail", project_id=journal.project.id)
        if journal.project.user != request.user:
            return redirect("fr.projects.detail", journal.project.id)

        reduced_minutes = journal.reduced_minutes
        content = request.POST.get("content", "")
        image_count = len(re.findall(IMAGE_REGEX, content))
        required_image_count = math.ceil(max(1, reduced_minutes / 180))

        content_length = _prose_length(content)

        if image_count < required_image_count:
            return self.get(
                request,
                journal.id,
                info=f"please add atleast {required_image_count - image_count} more image(s) to log this journal!",
                context={"content": content},
            )

        required_content_length = min(100, reduced_minutes // 3)
        if content_length < required_content_length:
            return self.get(
                request,
                journal.id,
                info=_prose_requirement(required_content_length, content_length),
                context={"content": content},
            )

        journal.content = content
        journal.save()

        log_to_channel(
            f":haiku: *Journal edited for {escape_mrkdwn(journal.project.project_name)}!*\n- {journal.reduced_minutes} minutes",
        )

        return self.get(request, journal.id, context={"success": True})
