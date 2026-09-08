from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from ...models import Project

PROJECTS_PER_PAGE = 120


class DiscoverView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        projects = Project.objects.select_related("user", "user__profile").order_by(
            "-created_at"
        )

        paginator = Paginator(projects, PROJECTS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page"))

        return render(
            request,
            "client/discover.html",
            {"projects": page_obj, "paginator": paginator},
        )
