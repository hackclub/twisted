from django.views import View
from django.shortcuts import render, redirect
from ...models import Project


class DiscoverView(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        projects = Project.objects.select_related("user", "user__profile").order_by(
            "-created_at"
        )

        return render(
            request,
            "client/discover.html",
            {"projects": projects},
        )
