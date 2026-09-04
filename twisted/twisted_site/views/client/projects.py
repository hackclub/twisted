from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from ...models import PROJECT_TYPE_CHOICES, Project


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

        return render(
            request,
            "client/projects/create.html",
            {"complete": False},
        )

    def post(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project_name = request.POST["name"]
        project_description = request.POST["description"]
        project_type = request.POST["type"]

        if project_type not in PROJECT_TYPE_CHOICES:
            return HttpResponse("naughty! you arent supposed to do this!")

        Project.objects.create(
            user=request.user,
            project_name=project_name,
            project_description=project_description,
            project_type=project_type,
        )

        return redirect("fr.projects")
