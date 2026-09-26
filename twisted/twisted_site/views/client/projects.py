
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render, resolve_url
from django.views import View

from twisted_site.models import PROJECT_TYPE_CHOICES, Project, as_user
from twisted_site.slack import log_to_channel


# Create your views here.
class ListProjects(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = as_user(request.user).profile

        projects = as_user(request.user).projects.all()

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

        submitted_name = request.POST.get("name")
        submitted_description = request.POST.get("description")
        project_name = submitted_name.strip() if submitted_name is not None else ""
        project_description = (
            submitted_description.strip() if submitted_description is not None else ""
        )
        project_type = request.POST.get("type")
        project_type = project_type if project_type is not None else ""

        if project_name == "" or project_description == "" or project_type == "":
            return HttpResponseBadRequest("Name, description, and type are required")

        if project_type not in PROJECT_TYPE_CHOICES:
            return HttpResponse("naughty! you arent supposed to do this!")

        project = Project.objects.create(
            user=request.user,
            project_name=project_name,
            project_description=project_description,
            project_type=project_type,
        )

        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"

        log_to_channel(
            f"*{as_user(request.user).profile.slack_username}* created a <{project_url}|new project>!\n- *Name*: {project_name}\n- *Description*: {project_description}\n- {project_type.title()}",
        )

        return redirect("fr.projects.detail", project.id)
