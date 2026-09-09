from typing import cast

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, resolve_url
from django.views import View

from ...models import PROJECT_TYPE_CHOICES, Profile, Project
from ...slack import log_to_channel


# Create your views here.
class ListProjects(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = cast(Profile, request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        projects = cast(QuerySet[Project], request.user.projects.all())  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        return render(
            request,
            "client/projects/list.html",
            {"profile": profile, "projects": projects},
        )


class CreateProject(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        return render(request, "client/projects/create.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project_name: str = request.POST["name"]
        project_description: str = request.POST["description"]
        project_type: str = request.POST["type"]

        if project_type not in PROJECT_TYPE_CHOICES:
            return HttpResponse("naughty! you arent supposed to do this!")

        project = Project.objects.create(
            user=request.user,
            project_name=project_name,
            project_description=project_description,
            project_type=project_type,
        )

        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]

        log_to_channel(
            f"*{request.user.profile.slack_username}* created a <{project_url}|new project>!\n- *Name*: {project_name}\n- *Description*: {project_description}\n- {project_type.title()}"  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        )

        return redirect("fr.projects.detail", project.id)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
