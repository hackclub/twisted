import os
import random

import requests
from authlib.integrations.django_client import OAuth
from django.contrib.auth import get_user_model, login, logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View

from ... import hackatime
from ...models import Profile
from ...slack import slack_bot

oauth = OAuth()

oauth.register(
    name="hca",
    server_metadata_url="https://auth.hackclub.com/.well-known/openid-configuration",
    client_id=os.environ["HCA_CLIENT_ID"],
    client_secret=os.environ["HCA_CLIENT_SECRET"],
    client_kwargs={
        "scope": "openid profile email phone address birthdate slack_id verification_status"
    },
)


class LoginView(View):
    def post(self, request):
        if (
            request.user.is_authenticated
            and request.user.profile.hackatime_access_token
        ):
            return redirect("dashboard")

        redirect_uri = os.environ["HCA_REDIRECT_URI"]

        response = oauth.hca.authorize_redirect(request, redirect_uri)
        return response


class AuthCallbackView(View):
    def get(self, request):
        if os.environ.get("LOGIN_ENABLED") == "false":
            return JsonResponse(
                {"error": "Not allowed! DM @kavyansh. if this is a mistake!"}
            )

        token = oauth.hca.authorize_access_token(request)

        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.hca.userinfo(token=token)

        email = userinfo.get("email", "hackclubber@example.com")
        name = userinfo.get("name", "")
        sub = userinfo.get("sub")
        clean_sub = sub.replace("!", "_")
        slack_id = userinfo.get("slack_id", "")
        verification_status = userinfo.get("verification_status", "")
        ysws_eligible = userinfo.get("ysws_eligible", False)
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=clean_sub,
            defaults={
                "email": email,
                "first_name": userinfo.get("given_name", ""),
                "last_name": userinfo.get("family_name", ""),
            },
        )

        display_name = name
        avatar_url = os.environ.get("DEFAULT_PFP", "")

        if slack_id:
            try:
                slack_user = slack_bot.users_info(user=slack_id)["user"]
                slack_profile = slack_user["profile"]

                display_name = slack_profile.get("display_name") or slack_profile.get(
                    "real_name"
                )
                avatar_url = slack_profile.get("image_512")

            except Exception as e:  # noqa: BLE001 - any Slack failure should fall back to the default name/pfp
                print("Slack profile fetch failed", e)

        profile, created = Profile.objects.get_or_create(user=user)  # ty:ignore[unresolved-attribute]
        profile.verification_status = verification_status
        profile.slack_id = slack_id
        profile.slack_username = display_name
        profile.slack_pfp_url = avatar_url
        profile.ysws_eligible = ysws_eligible
        profile.hca_access_token = token["access_token"]

        referral_code = self.request.COOKIES.get("referral")
        if created and referral_code:
            referral_profiles = Profile.objects.filter(my_referral_code=referral_code)
            if referral_profiles:
                referral_profile = referral_profiles.get()
                profile.referred_by = referral_profile

        profile.save()

        if os.environ.get("LOGIN_ENABLED") == "maybe" and not profile.is_allowed:
            return JsonResponse(
                {"error": "Not allowed! DM @kavyansh. if this is a mistake!"}
            )

        login(request, user)

        if not profile.hackatime_access_token:
            HACKATIME_CLIENT_ID = os.environ["HACKATIME_CLIENT_ID"]
            HACKATIME_REDIRECT_URI = os.environ["HACKATIME_REDIRECT_URI"]
            scopes = "profile+read"

            profile.hackatime_state = str(random.randint(0, 10**20))
            profile.save()

            return redirect(
                f"https://hackatime.hackclub.com/oauth/authorize?client_id={HACKATIME_CLIENT_ID}&redirect_uri={HACKATIME_REDIRECT_URI}&response_type=code&scope={scopes}&state={profile.hackatime_state}"
            )

        return redirect("dashboard")


class HackatimeCallbackView(View):
    def get(self, request):
        if os.environ.get("LOGIN_ENABLED") == "false":
            return JsonResponse("not allowed!")

        profile = request.user.profile

        state = request.GET["state"]
        if state != profile.hackatime_state:
            profile.hackatime_state = ""
            profile.save()
            return JsonResponse(
                {
                    "error": "State mismatch; Auth failed. Please contact support with the error code if this is unexpected!"
                }
            )
        profile.hackatime_state = ""
        profile.save()

        code = request.GET["code"]
        HACKATIME_CLIENT_ID = os.environ["HACKATIME_CLIENT_ID"]
        HACKATIME_CLIENT_SECRET = os.environ["HACKATIME_CLIENT_SECRET"]
        HACKATIME_REDIRECT_URI = os.environ["HACKATIME_REDIRECT_URI"]
        resp = requests.post(
            "https://hackatime.hackclub.com/oauth/token",
            data={
                "client_id": HACKATIME_CLIENT_ID,
                "client_secret": HACKATIME_CLIENT_SECRET,
                "code": code,
                "redirect_uri": HACKATIME_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = data["access_token"]

        me = hackatime.me(access_token)
        if profile.slack_id != me.slack_id:
            return JsonResponse(
                {
                    "error": "Slack ID mismatch. Please contact support with the error code if this is unexpected!"
                }
            )

        profile.hackatime_access_token = access_token
        profile.save()
        return redirect("dashboard")


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("homepage")
