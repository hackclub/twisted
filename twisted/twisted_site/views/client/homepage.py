from django.views import View
from django.shortcuts import render
import os


# Create your views here.
class HomepageView(View):
    def get(self, request):
        if os.environ.get("LOGIN_ENABLED") == "false":
            login_enabled = False
        else:
            login_enabled = True
        
        referral_code = request.GET.get("ref")
        
        response = render(
            request,
            "client/homepage.html",
            {"login_enabled": login_enabled},
        )
        
        if referral_code:
            response.set_cookie(
                'referral',
                referral_code,
                max_age=60*60, # 1 hour
                httponly=True,
                samesite='Lax'
            )

        return response


class FaqsView(View):
    def get(self, request):
        return render(request, "client/faqs.html")
