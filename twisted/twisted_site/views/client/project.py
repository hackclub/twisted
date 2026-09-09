from itertools import chain
from operator import attrgetter
from typing import cast

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View
from requests import HTTPError, RequestException

from ... import ari, hackatime
from ...models import (
    PROJECT_TYPE_CHOICES,
    Profile,
    Project,
    ProjectShip,
    TemplateContext,
)
from ...slack import log_to_channel


def _or_none(value: str) -> str:
    """Renders an optional display string, falling back to "None"."""
    return value if value != "" else "None"


# Create your views here.
class ProjectDetail(View):
    def get(self, request: HttpRequest, id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = TemplateContext()

        profile = cast(Profile, request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        context["profile"] = profile

        project = get_object_or_404(Project, id=id)
        context["project"] = project

        journals = project.journals.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        ships = project.ships.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        context["journals"] = list(chain(journals, ships))
        context["journals"].sort(key=attrgetter("created_at"), reverse=True)

        context["first_pass_status"] = "pending"
        context["second_pass_status"] = "pending"

        if project.latest_ship() is not None:
            try:
                status = ari.get_project_status(project)
                context["first_pass_status"], context["second_pass_status"] = (
                    ari.ship_passes_from_status(status)
                )
            except RequestException:
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
    def get(self, request: HttpRequest, id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = TemplateContext()

        project = get_object_or_404(Project, id=id)
        context["project"] = project

        if project.is_shipped():
            return redirect("fr.projects.detail", id)

        if project.user != request.user:
            return redirect("dashboard")

        profile = cast(Profile, request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        context["profile"] = profile

        try:
            context["hackatime_projects"] = hackatime.projects(
                profile.hackatime_access_token
            )
        except HTTPError:
            no_projects: list[hackatime.HackatimeProject] = []
            context["hackatime_projects"] = no_projects

        return render(
            request,
            "client/projects/settings.html",
            context,
        )

    def post(self, request: HttpRequest, id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.is_shipped():
            return redirect("fr.projects.detail", id)

        project_type = request.POST["type"]
        if project_type not in PROJECT_TYPE_CHOICES:
            return HttpResponse("naughty! you arent supposed to do this!")

        project.project_name = request.POST["name"]
        project.project_description = request.POST["description"]
        project.project_type = project_type
        project.hackatime_project_name = request.POST.get("hackatime", "")
        project.repo_url = request.POST["repo"]
        project.playable_url = request.POST.get("playable_url", "")
        project.screenshot_url = request.POST.get("screenshot_url", "")
        project.save()

        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
        log_to_channel(
            f":settings: Updated settings for *<{project_url}|{project.project_name}>*!\n- *Description*: {project.project_description}\n- *Type*: {project_type}\n- *Hackatime*: {_or_none(project.hackatime_project_name)}\n- *Repo*: {_or_none(project.repo_url)}\n- *Demo*: {_or_none(project.playable_url)}\n- *Screenshot*: {_or_none(project.screenshot_url)}"
        )

        return redirect("fr.projects.detail", project.id)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]


class SubmitProject(View):
    def get(
        self,
        request: HttpRequest,
        id: int,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = TemplateContext()

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.playable_url == "":
            return redirect("fr.projects.detail", id)

        if project.screenshot_url == "":
            return redirect("fr.projects.detail", id)

        if not project.user.profile.ysws_eligible:  # pyrefly: ignore[missing-attribute]
            context["info"] = (
                "You are not YSWS eligible yet! Please get IDVd! Get help with it at #identity-help! (if you think this is a mistake, please ask in #twisted-help)"
            )

        context["project"] = project
        return render(request, "client/projects/ship.html", context)

    def post(
        self,
        request: HttpRequest,
        id: int,
        context: TemplateContext | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = TemplateContext()

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=id)
        if project.user != request.user:
            return redirect("fr.projects.detail", project.id)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]

        if project.is_shipped():
            return self.get(
                request, id, context={"info": "silly! you have already shipped."}
            )

        if project.playable_url == "":
            return redirect("fr.projects.detail", id)

        if project.screenshot_url == "":
            return redirect("fr.projects.detail", id)

        if not project.user.profile.ysws_eligible:  # pyrefly: ignore[missing-attribute]
            return self.get(request, id)

        ship = ProjectShip(project=project)
        ship.save()
        try:
            ari.send_ship(ship)
        except Exception:
            _ = ship.delete()
            raise

        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
        log_to_channel(
            f":shipitparrot: Project *<{project_url}|{project.project_name}> shipped with *{project.time_logged()} minutes*"
        )

        return redirect("fr.projects.detail", project.id)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
