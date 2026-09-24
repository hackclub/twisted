from itertools import chain
from operator import attrgetter

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View
from requests import HTTPError, RequestException

from twisted_site import ari, hackatime
from twisted_site.models import (
    PROJECT_TYPE_CHOICES,
    Project,
    ProjectShip,
    TemplateContext,
    as_user,
)
from twisted_site.slack import log_to_channel

logger = getLogger(__name__)


def _or_none(value: str) -> str:
    """Renders an optional display string, falling back to "None"."""
    return value if value != "" else "None"


# Create your views here.
class ProjectDetail(View):
    def get(self, request: HttpRequest, project_id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = TemplateContext()

        profile = as_user(request.user).profile
        context["profile"] = profile

        project = get_object_or_404(Project, id=project_id)
        context["project"] = project

        journals = project.journals.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        ships = project.ships.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        context["journals"] = list(chain(journals, ships))
        context["journals"].sort(key=attrgetter("created_at"), reverse=True)

        context["first_pass_status"] = "pending"
        context["second_pass_status"] = "pending"

        if project.latest_ship() is not None:
            if ari.is_configured():
                try:
                    status = ari.get_project_status(project)
                    context["first_pass_status"], context["second_pass_status"] = (
                        ari.ship_passes_from_status(status)
                    )
                except RequestException:
                    logger.warning("Unable to load ARI status for project %s", project.id)
                    context["first_pass_status"] = "unavailable"
                    context["second_pass_status"] = "unavailable"
                except Exception:
                    logger.exception(
                        "Unexpected error loading ARI status for project %s",
                        project.id,
                    )
                    context["first_pass_status"] = "unavailable"
                    context["second_pass_status"] = "unavailable"
            else:
                context["first_pass_status"] = "unavailable"
                context["second_pass_status"] = "unavailable"

        if project.user == request.user:
            context["owner"] = True
        else:
            context["owner"] = False

        return render(
            request,
            "client/projects/detail.html",
            context,
        )


class ProjectSettings(View):
    def get(self, request: HttpRequest, project_id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = TemplateContext()

        project = get_object_or_404(Project, id=project_id)
        context["project"] = project

        if project.is_shipped():
            return redirect("fr.projects.detail", project_id)

        if project.user != request.user:
            return redirect("dashboard")

        profile = as_user(request.user).profile
        context["profile"] = profile

        try:
            context["hackatime_projects"] = hackatime.projects(profile.hackatime_access_token)
        except HTTPError:
            no_projects: list[hackatime.HackatimeProject] = []
            context["hackatime_projects"] = no_projects

        return render(
            request,
            "client/projects/settings.html",
            context,
        )

    def post(self, request: HttpRequest, project_id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.is_shipped():
            return redirect("fr.projects.detail", project_id)

        project_type = request.POST["type"]
        if project_type not in PROJECT_TYPE_CHOICES:
            return HttpResponse("naughty! you arent supposed to do this!")

        project.project_name = request.POST["name"]
        project.project_description = request.POST["description"]
        project.project_type = project_type
        project.hackatime_project_names = request.POST.getlist("hackatime")
        project.repo_url = request.POST["repo"]
        project.playable_url = request.POST.get("playable_url", "")
        project.screenshot_url = request.POST.get("screenshot_url", "")
        project.save()

        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"
        hackatime_names = ", ".join(project.hackatime_project_names)
        log_to_channel(
            f":settings: Updated settings for *<{project_url}|{project.project_name}>*!\n- *Description*: {project.project_description}\n- *Type*: {project_type}\n- *Hackatime*: {_or_none(hackatime_names)}\n- *Repo*: {_or_none(project.repo_url)}\n- *Demo*: {_or_none(project.playable_url)}\n- *Screenshot*: {_or_none(project.screenshot_url)}",
        )

        return redirect("fr.projects.detail", project.id)


class SubmitProject(View):
    def get(
        self,
        request: HttpRequest,
        project_id: int,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = TemplateContext()

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.playable_url == "":
            return redirect("fr.projects.detail", project_id)

        if project.screenshot_url == "":
            return redirect("fr.projects.detail", project_id)

        if not as_user(project.user).profile.ysws_eligible:
            context["info"] = (
                "You are not YSWS eligible yet! Please get IDVd! Get help with it at #identity-help! (if you think this is a mistake, please ask in #twisted-help)"
            )

        context["project"] = project
        return render(request, "client/projects/ship.html", context)

    def post(
        self,
        request: HttpRequest,
        project_id: int,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = TemplateContext()

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return redirect("fr.projects.detail", project.id)

        if project.is_shipped():
            return self.get(
                request,
                project_id,
                context={"info": "silly! you have already shipped."},
            )

        if project.playable_url == "":
            return redirect("fr.projects.detail", project_id)

        if project.screenshot_url == "":
            return redirect("fr.projects.detail", project_id)

        if not as_user(project.user).profile.ysws_eligible:
            return self.get(request, project_id)

        if not ari.is_configured():
            context["info"] = (
                "The project submission service is temporarily unavailable. "
                "Your project was not submitted; please try again later."
            )
            return self.get(request, project_id, context=context)

        ship = ProjectShip(project=project)
        ship.save()
        try:
            ari.send_ship(ship)
        except Exception:
            _ = ship.delete()
            logger.exception("Failed to submit project %s to ARI", project.id)
            context["info"] = (
                "The project submission service is temporarily unavailable. "
                "Your project was not submitted; please try again later."
            )
            return self.get(request, project_id, context=context)

        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"
        log_to_channel(
            f":shipitparrot: Project *<{project_url}|{project.project_name}> shipped with *{project.time_logged()} minutes*",
        )

        return redirect("fr.projects.detail", project.id)
