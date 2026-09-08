from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.shortcuts import render, redirect
from ...models import Pathway


# Create your views here.
class PathwaysView(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = request.user.profile
        pathways = Pathway.objects.order_by("start").all()

        current_pathways = []
        past_pathways = []
        future_pathways = []

        for pathway in pathways:
            minutes_spent = pathway.mins_spent(request.user)
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
