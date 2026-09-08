from itertools import chain

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View
from requests import HTTPError, RequestException

from ... import ari, hackatime
from ...models import PROJECT_TYPE_CHOICES, Profile, Project, ProjectShip
from ...slack import log_to_channel


# Create your views here.
class ProjectDetail(View):
    def get(self, request: HttpRequest, id: int) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = {}

        profile = request.user.profile
        assert isinstance(profile, Profile)
        context["profile"] = profile

        project = get_object_or_404(Project, id=id)
        context["project"] = project

        journals = project.journals.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        ships = project.ships.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        context["journals"] = list(chain(journals, ships))
        context["journals"].sort(key=lambda x: x.created_at, reverse=True)

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

        context = {}

        project = get_object_or_404(Project, id=id)
        context["project"] = project

        if project.is_shipped():
            return redirect("fr.projects.detail", id)

        if project.user != request.user:
            return redirect("dashboard")

        profile = request.user.profile
        context["profile"] = profile

        try:
            context["hackatime_projects"] = hackatime.projects(
                profile.hackatime_access_token
            )
        except HTTPError:
            context["hackatime_projects"] = []

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
            f":settings: Updated settings for *<{project_url}|{project.project_name}>*!\n- *Description*: {project.project_description}\n- *Type*: {project_type}\n- *Hackatime*: {project.hackatime_project_name or 'None'}\n- *Repo*: {project.repo_url or 'None'}\n- *Demo*: {project.playable_url or 'None'}\n- *Screenshot*: {project.screenshot_url}"
        )

        return redirect("fr.projects.detail", project.id)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]


class SubmitProject(View):
    def get(
        self, request: HttpRequest, id: int, context: TemplateContext | None = None  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = {}

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=id)
        if project.user != request.user:
            return redirect("dashboard")

        if not project.playable_url:
            return redirect("fr.projects.detail", id)

        if not project.screenshot_url:
            return redirect("fr.projects.detail", id)

        if not project.user.profile.ysws_eligible:  # pyrefly: ignore[missing-attribute]
            context["info"] = (
                "You are not YSWS eligible yet! Please get IDVd! Get help with it at #identity-help! (if you think this is a mistake, please ask in #twisted-help)"
            )

        context["project"] = project
        return render(request, "client/projects/ship.html", context)

    def post(
        self, request: HttpRequest, id: int, context: TemplateContext | None = None  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if context is None:
            context = {}

        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = get_object_or_404(Project, id=id)
        if project.user != request.user:
            return redirect("fr.projects.detail", project.id)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]

        if project.is_shipped():
            return self.get(
                request, id, context={"info": "silly! you have already shipped."}
            )

        if not project.playable_url:
            return redirect("fr.projects.detail", id)

        if not project.screenshot_url:
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
