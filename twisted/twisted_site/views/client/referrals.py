import random
import string

from django.shortcuts import redirect, render
from django.views import View

from ...models import Profile


# Create your views here.
class ReferralsView(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context = {}

        context["profile"] = profile = request.user.profile

        if not profile.my_referral_code:
            while True:
                current_code = "".join(
                    [
                        random.choice(string.ascii_letters + string.digits)
                        for _ in range(12)
                    ]
                )
                if len(Profile.objects.filter(my_referral_code=current_code)) == 0:
                    profile.my_referral_code = current_code
                    profile.save()
                    break

        return render(request, "client/referrals.html", context=context)
