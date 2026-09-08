from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View

from ...models import Project


# Create your views here.
class DashboardView(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")
        profile = self.request.user.profile  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        context = {"profile": profile}

        startup_windows = []

        project_id = request.GET.get("project")

        if project_id not in (None, ""):
            project = get_object_or_404(Project, id=project_id)
            startup_windows.append(
                {
                    "href": resolve_url("fr.projects.detail", project.id),  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                    "title": project.project_name,
                }
            )

        if request.GET.get("discover") is not None:
            startup_windows.append(
                {"href": resolve_url("fr.discover"), "title": "discover"}
            )

        context["startup_windows"] = startup_windows

        return render(request, "client/dashboard.html", context)
