from typing import cast

from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from ...models import Pathway, Profile


# Create your views here.
class PathwaysView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = cast("Profile", request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        pathways = Pathway.objects.order_by("start").all()

        current_pathways: list[dict[str, Pathway | int | bool]] = []
        past_pathways: list[dict[str, Pathway | int | bool]] = []
        future_pathways: list[dict[str, Pathway | int | bool]] = []

        for pathway in pathways:
            minutes_spent = pathway.mins_spent(cast("AbstractBaseUser", request.user))
            pathway_info = {
                "pathway": pathway,
                "minutes_spent": minutes_spent,
                "unlocked": minutes_spent > pathway.min_mins,
            }
            if pathway.in_progress():
                current_pathways.append(pathway_info)
            if pathway.ended():
                past_pathways.append(pathway_info)
            if pathway.didnt_start():
                future_pathways.append(pathway_info)

        past_pathways.reverse()

        return render(
            request,
            "client/pathways.html",
            {
                "profile": profile,
                "pathways": pathways,
                "current_pathways": current_pathways,
                "past_pathways": past_pathways,
                "future_pathways": future_pathways,
            },
        )
