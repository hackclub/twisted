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
        profile = as_user(self.request.user).profile

        ctx = {}
        ctx["profile"] = profile

        profiles = []

        # 0 = twists
        # 1 = time
        # 2 = total time

        modee = request.GET.get("mode");
          
        ctx["mode"] = int(modee) if modee else 0;

        print(f"Mode: {ctx["mode"]}")

        for profile in Profile.objects.iterator():
            profiles.append(profile)

        # test1 = Profile()
        # test1.twists = 12431;
        # test1.user = User();
        # test1.slack_username = "test1"
        # profiles.append(test1)

        # test2 = Profile()
        # test2.twists = 4;
        # test2.user = User();
        # test2.slack_username = "test2"
        # profiles.append(test2)

        # test3 = Profile()
        # test3.twists = 199999999999;
        # test3.user = User();
        # test3.slack_username = "test3"
        # profiles.append(test3)

        def twists(profile: Profile):
            return profile.twists;
        def hours(profile: Profile):
            return profile.time_shipped();
        def totalhours(profile: Profile):
            return profile.time_logged();

        sortedL = []
        match ctx["mode"]:
            case 0:
                sortedL = sorted(profiles, key=twists);
            case 1:
                sortedL = sorted(profiles, key=hours);
            case 2:
                sortedL = sorted(profiles, key=totalhours);
        
        sortedL.reverse()

        sortedL.index

        ctx["page"] = sortedL[0 : 5]
        print(ctx["page"])
        if profile in sortedL:
            ctx["yourrank"] = sortedL.index(profile) + 1
        else: ctx["yourrank"] = -1

        return render(request, "client/leaderboard.html", ctx)
