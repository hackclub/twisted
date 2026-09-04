from requests import HTTPError
from itertools import chain
from markdown_it.rules_inline import image
from django.http import JsonResponse
from django.views import View
from django.shortcuts import render, redirect

from ...models import Profile, Project, Journal, ProjectShip
from ... import hackatime
from ... import ari

# Create your views here.
class ProjectDetail(View):
    def get(self, request, id):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = {}

        profile: Profile = request.user.profile
        context["profile"] = profile

        project = Project.objects.get(id=id)
        context["project"] = project

        journals = project.journals.all()
        ships = project.ships.all()

        context["journals"] = list(chain(journals, ships))
        context["journals"].sort(key=lambda x: x.created_at, reverse=True)

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
    def get(self, request, id):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = {}

        project = Project.objects.get(id=id)
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

    def post(self, request, id):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = Project.objects.get(id=id)
        if project.user != request.user:
            return redirect("dashboard")

        if project.is_shipped():
            return redirect("fr.projects.detail", id)

        project.project_name = request.POST["name"]
        project.project_description = request.POST["description"]
        project.project_type = request.POST["type"]
        project.hackatime_project_name = request.POST.get("hackatime", "")
        project.repo_url = request.POST["repo"]
        project.playable_url = request.POST.get("playable_url", "")
        project.screenshot_url = request.POST.get("screenshot_url", "")
        project.save()
        return redirect("fr.projects.detail", project.id)


class SubmitProject(View):
    def get(self, request, id, context={}):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = Project.objects.get(id=id)
        if project.user != request.user:
            return redirect("dashboard")

        if not project.playable_url:
            return redirect("fr.projects.detail", id)

        if not project.screenshot_url:
            return redirect("fr.projects.detail", id)

        if not project.user.profile.ysws_eligible:
            context["info"] = (
                "You are not YSWS eligible yet! Please get IDVd! Get help with it at #identity-help! (if you think this is a mistake, please ask in #twisted-help)"
            )

        context["project"] = project
        return render(request, "client/projects/ship.html", context)

    def post(self, request, id, context={}):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        project = Project.objects.get(id=id)
        if project.user != request.user:
            return redirect('fr.project.detail', project.id)

        if project.is_shipped():
            return self.get(
                request, id, context={"info": "silly! you have already shipped."}
            )

        if not project.playable_url:
            return redirect("fr.projects.detail", id)

        if not project.screenshot_url:
            return redirect("fr.projects.detail", id)

        if not project.user.profile.ysws_eligible:
            return self.get(request, id)

        ship = ProjectShip(project=project)
        ship.save()
        try:
            ari.send_ship(ship)
        except Exception as e:
            ship.delete()
            raise e
        return redirect('fr.projects.detail', project.id)
