from typing import TYPE_CHECKING, cast

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from twisted_site.models import Pathway, PathwayTimeSpent, Profile

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser


# Create your views here.
class PathwaysView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = cast("Profile", request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        pathways = Pathway.objects.order_by("start").all()

        time_spent_lookup = {
            ts.pathway_id: ts
            for ts in PathwayTimeSpent.objects.filter(user=request.user, pathway__in=pathways)
        }

        current_pathway = None
        current_pathways: list[dict[str, Pathway | int | bool | PathwayTimeSpent | None]] = []
        past_pathways: list[dict[str, Pathway | int | bool | PathwayTimeSpent | None]] = []
        future_pathways: list[dict[str, Pathway | int | bool | PathwayTimeSpent | None]] = []

        for pathway in pathways:
            minutes_spent = pathway.mins_spent(cast("AbstractBaseUser", request.user))
            pathway_info = {
                "pathway": pathway,
                "minutes_spent": minutes_spent,
                "unlocked": minutes_spent > pathway.min_mins,
                "time_spent": time_spent_lookup.get(pathway.id),
            }
            if pathway.in_progress():
                current_pathway = pathway
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
                "unspent_mins": current_pathway.get_unspent_mins(request.user),
                "past_pathways": past_pathways,
                "future_pathways": future_pathways,
            },
        )


class UnlockPathway(View):
    def post(self, request: HttpRequest, pathway_id: int) -> HttpResponse:
        if request.user.is_anonymous:
            return redirect("homepage")

        pathway = get_object_or_404(Pathway, id=pathway_id)

        if not pathway.in_progress():
            return redirect("fr.pathways")

        already_unlocked = PathwayTimeSpent.objects.filter(
            pathway=pathway, user=request.user, unlocked=True,
        ).exists()
        if already_unlocked:
            return redirect("fr.pathways")

        unspent_mins = pathway.get_unspent_mins(request.user)
        if unspent_mins < pathway.min_mins:
            return redirect("fr.pathways")

        PathwayTimeSpent.objects.update_or_create(
            pathway=pathway,
            user=request.user,
            defaults={"unlocked": True, "minutes": pathway.min_mins},
        )

        return redirect("fr.pathways")
