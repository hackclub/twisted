from typing import Any, cast

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View

from ...models import Profile, Project


# Create your views here.
class DashboardView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")
        profile = cast(Profile, self.request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        context: dict[str, Any] = {"profile": profile}  # pyrefly: ignore[explicit-any]

        startup_windows: list[dict[str, str]] = []

        project_id: str | None = request.GET.get("project")

        if project_id not in (None, ""):
            project = get_object_or_404(Project, id=project_id)
            startup_windows.append(
                {
                    "href": resolve_url("fr.projects.detail", project.id),  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                    "title": project.project_name,
                }
            )

        if request.GET.get("discover") is not None:
            startup_windows.append({"href": resolve_url("fr.discover"), "title": "discover"})

        context["startup_windows"] = startup_windows

        return render(request, "client/dashboard.html", context)
