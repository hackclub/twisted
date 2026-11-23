import math
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views import View

from twisted_site.models import Profile, Project, User, as_user
import random


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
        pagee = request.GET.get("page");
        page = int(pagee) if pagee else 1;
          
        ctx["mode"] = int(modee) if modee else 0;


        for profile in Profile.objects.iterator():
            if not profile.leaderboard_banned and profile.leaderboard_opted:
                profiles.append(profile)

        for i in range(500):
            test1 = Profile()
            rand = random.randint(1,100000)
            test1.twists = rand;
            test1.user = User(rand);
            test1.slack_username = f"test{rand}"
            profiles.append(test1)

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

        maxPage = math.ceil(len(sortedL)/5);
        if (page <= 0 or page >= maxPage):
            page = maxPage
            ctx["lastPage"] = True

        pageOffset = (page -1) * 5;
        ctx["page"] = sortedL[(5 * (page -1)) : page * 5]
        ctx["pageOffset"] = pageOffset
        ctx["pageNum"] = page
        print(ctx["page"])
        if profile in sortedL:
            ctx["yourrank"] = sortedL.index(profile) + 1
        else: ctx["yourrank"] = -1

        print(f"Mode: {ctx["mode"]}, Page: {page}, Offset: {pageOffset}")
        return render(request, "client/leaderboard.html", ctx)

    def post(self, request: HttpRequest) -> HttpResponse | None:
            if self.request.user.is_anonymous:
                return HttpResponse("err")
    
            prf: Profile = get_object_or_404(Profile, id=self.request.user.id)
            prf.leaderboard_opted = request.POST.get("opt") == "True"
            prf.save()
    
            return redirect(self.request.path)