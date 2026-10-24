from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View

from twisted_site.models import Project, as_user


# Create your views here.
class DashboardView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")
        profile = as_user(self.request.user).profile

        context: dict[str, Any] = {"profile": profile}  # pyrefly: ignore[explicit-any]

        startup_windows: list[dict[str, str]] = []

        project_id: str | None = request.GET.get("project")

        specified_startup_windows: str | None = request.GET.getlist("windows")
        fullscreen_startup_window: bool | None = request.GET.get("fullscreen_win")

        if (specified_startup_windows):
            x = 50
            y = 50
            for win in specified_startup_windows:
                startup_windows.append(
                                                                {
                                                                    "href": resolve_url(f"fr.{win}"),
                                                                    "x": x,
                                                                    "y": y,
                                                                    "fullscreen": fullscreen_startup_window
                                                                },
                                                            )
                x += 30
                y += 30


        if project_id not in (None, ""):
            try:
                project_pk = int(project_id)
            except ValueError:
                project_pk = None
            if project_pk is not None:
                project = get_object_or_404(Project, id=project_pk)
                startup_windows.append(
                    {
                        "href": resolve_url("fr.projects.detail", project.id),
                        "title": project.project_name,
                    },
                )

        if request.GET.get("discover") is not None:
            startup_windows.append({"href": resolve_url("fr.discover"), "title": "discover"})

        context["startup_windows"] = startup_windows

        return render(request, "client/dashboard.html", context)
