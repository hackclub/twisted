from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View

from twisted_site.models import Profile, Project, User, as_user


# Create your views here.
class LeaderboardView(View):

    

    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        ctx = {}

        profiles = []

        for profile in Profile.objects.iterator():
            profiles.append(profile)

        test1 = Profile()
        test1.twists = 12431;
        test1.user = User();
        test1.slack_username = "test1"
        profiles.append(test1)

        test2 = Profile()
        test2.twists = 4;
        test2.user = User();
        test2.slack_username = "test2"
        profiles.append(test2)

        test3 = Profile()
        test3.twists = 199999999999;
        test3.user = User();
        test3.slack_username = "test3"
        profiles.append(test3)

        def twists(profile: Profile):
                return profile.twists;

        sortedL = sorted(profiles, key=twists);
        sortedL.reverse()

        ctx["page"] = sortedL[0 : 5]
        print(ctx["page"])
        

        return render(request, "client/leaderboard.html", ctx)
