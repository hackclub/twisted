from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View
from django.shortcuts import render, redirect, resolve_url
from ...models import Project, PROJECT_TYPE_CHOICES
from ...slack import log_to_channel

# Create your views here.
class ListProjects(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = request.user.profile

        projects = request.user.projects.all()

        return render(
            request,
            "client/projects/list.html",
            {"profile": profile, "projects": projects},
        )


class CreateProject(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        return render(request, "client/projects/create.html")

    def post(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project_name = request.POST["name"]
        project_description = request.POST["description"]
        project_type = request.POST["type"]

        if project_type not in PROJECT_TYPE_CHOICES:
            return HttpResponse("naughty! you arent supposed to do this!")

        
        project = Project.objects.create(
            user=request.user,
            project_name=project_name,
            project_description=project_description,
            project_type=project_type,
        )
        
        project_url = f"{self.request.scheme}://{self.request.get_host()}{resolve_url('dashboard')}?project={project.id}"
        
        log_to_channel(f"*{request.user.profile.slack_username}* created a <{project_url}|new project>!\n- *Name*: {project_name}\n- *Description*: {project_description}\n- {project_type.title()}")

        return redirect('fr.projects.detail', project.id)
