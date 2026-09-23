from django.urls import reverse
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from twisted_site.models import Pathway, Profile, Project, ShopRegion

PROJECTS_PER_PAGE = 120


class ShopView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = {}

        regions = ShopRegion.objects.all()
        context["regions"] = regions
        pathways = Pathway.objects.filter(start__lt=timezone.now(), pathwaytimespent__user=request.user, pathwaytimespent__unlocked=True)
        context["pathways"] = pathways

        return render(
            request,
            "client/shop.html",
            context,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        if request.POST.get("action") == "setRegion":
            profile: Profile = self.request.user.profile
            profile.region = ShopRegion.objects.get(id=request.POST["region"])
            profile.save()

            return redirect(request.path_info)

        return redirect(request.path_info)
