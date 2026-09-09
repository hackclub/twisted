import hmac
import logging
import os
import secrets
from typing import Any, NoReturn, cast

import requests
from authlib.integrations.base_client import (  # pyrefly: ignore[untyped-import]
    MismatchingStateError,
)
from authlib.integrations.django_client import OAuth  # pyrefly: ignore[untyped-import]
from django.contrib.auth import get_user_model, login, logout
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views import View

from twisted_site import hackatime
from twisted_site.models import Profile
from twisted_site.slack import log_to_channel, slack_bot

logger = logging.getLogger(__name__)


def _raise_type_error(msg: str) -> NoReturn:
    raise TypeError(msg)


oauth = OAuth()

oauth.register(
    name="hca",
    server_metadata_url="https://auth.hackclub.com/.well-known/openid-configuration",
    client_id=os.environ["HCA_CLIENT_ID"],
    client_secret=os.environ["HCA_CLIENT_SECRET"],
    client_kwargs={
        "scope": "openid profile email phone address birthdate slack_id verification_status",
    },
)


class LoginView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        if (
            request.user.is_authenticated and request.user.profile.hackatime_access_token  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        ):
            return redirect("dashboard")

        redirect_uri = os.environ["HCA_REDIRECT_URI"]

        return cast("HttpResponse", oauth.hca.authorize_redirect(request, redirect_uri))


class AuthCallbackView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if os.environ.get("LOGIN_ENABLED") == "false":
            return JsonResponse({"error": "Not allowed! DM @kavyansh. if this is a mistake!"})

        try:
            token = cast("dict[str, Any]", oauth.hca.authorize_access_token(request))
        except MismatchingStateError:
            return JsonResponse(
                {"error": "State mismatch; Auth failed. This may be due to a timeout, try again!"},
            )

        userinfo = cast("dict[str, Any] | None", token.get("userinfo"))
        if userinfo is None or len(userinfo) == 0:
            userinfo = cast("dict[str, Any]", oauth.hca.userinfo(token=token))

        email = userinfo.get("email", "hackclubber@example.com")
        name = cast("str", userinfo.get("name", ""))
        sub = cast("str", userinfo.get("sub"))
        clean_sub = sub.replace("!", "_")
        slack_id = userinfo.get("slack_id", "")
        if not slack_id:
            return JsonResponse(
                {
                    "error": "Twisted requires a Slack account linked to Hack Club Identity. "
                    "Please sign up for Slack and link it at https://auth.hackclub.com, then try logging in again.",
                },
            )

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

        try:
            raw_slack_user = slack_bot.users_info(user=slack_id)["user"]
            if not isinstance(raw_slack_user, dict):
                msg = "Slack users_info missing user"
                _raise_type_error(msg)

            slack_user = cast("dict[str, Any]", raw_slack_user)
            slack_profile = slack_user["profile"]
            if not isinstance(slack_profile, dict):
                msg = "Slack user missing profile"
                _raise_type_error(msg)

            display_name = cast("str | None", slack_profile.get("display_name"))
            if display_name in (None, ""):
                display_name = cast("str | None", slack_profile.get("real_name"))
            if display_name in (None, ""):
                display_name = name
            avatar_url = cast("str | None", slack_profile.get("image_512"))
            if avatar_url in (None, ""):
                avatar_url = os.environ["DEFAULT_PFP"]

        except Exception:
            logger.exception("Slack profile fetch failed")
            display_name = name
            avatar_url = os.environ["DEFAULT_PFP"]

        profile, created = Profile.objects.get_or_create(user=user)
        profile.verification_status = verification_status
        profile.slack_id = slack_id
        profile.slack_username = display_name
        profile.slack_pfp_url = avatar_url
        profile.ysws_eligible = ysws_eligible
        profile.hca_access_token = token["access_token"]

        referral_code = self.request.COOKIES.get("referral")
        if created and referral_code not in (None, ""):
            referral_profiles = Profile.objects.filter(my_referral_code=referral_code)
            if referral_profiles.exists():
                referral_profile = referral_profiles.get()
                profile.referred_by = referral_profile

        profile.save()

        if os.environ.get("LOGIN_ENABLED") == "maybe" and not profile.is_allowed:
            return JsonResponse({"error": "Not allowed! DM @kavyansh. if this is a mistake!"})

        login(request, user)

        if profile.hackatime_access_token == "":
            hackatime_client_id = os.environ["HACKATIME_CLIENT_ID"]
            hackatime_redirect_uri = os.environ["HACKATIME_REDIRECT_URI"]
            scopes = "profile+read"

            profile.hackatime_state = secrets.token_urlsafe(32)
            profile.save()

            return redirect(
                f"https://hackatime.hackclub.com/oauth/authorize?client_id={hackatime_client_id}&redirect_uri={hackatime_redirect_uri}&response_type=code&scope={scopes}&state={profile.hackatime_state}",
            )

        log_to_channel(f":ms-arrow-up-right: *{profile.slack_username}* just logged in!")

        return redirect("dashboard")


class HackatimeCallbackView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if os.environ.get("LOGIN_ENABLED") == "false":
            return JsonResponse("not allowed!")

        profile = cast("Profile", request.user.profile)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        state = request.GET["state"]
        if not hmac.compare_digest(state, profile.hackatime_state):
            profile.hackatime_state = ""
            profile.save()
            return JsonResponse(
                {
                    "error": "State mismatch; Auth failed. Please contact support with the error code if this is unexpected!",
                },
            )
        profile.hackatime_state = ""
        profile.save()

        code = request.GET["code"]
        hackatime_client_id = os.environ["HACKATIME_CLIENT_ID"]
        hackatime_client_secret = os.environ["HACKATIME_CLIENT_SECRET"]
        hackatime_redirect_uri = os.environ["HACKATIME_REDIRECT_URI"]
        resp = requests.post(
            "https://hackatime.hackclub.com/oauth/token",
            data={
                "client_id": hackatime_client_id,
                "client_secret": hackatime_client_secret,
                "code": code,
                "redirect_uri": hackatime_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = cast("str", data["access_token"])

        me = hackatime.me(access_token)
        if profile.slack_id != me.slack_id:
            return JsonResponse(
                {
                    "error": "Slack ID mismatch. Please contact support with the error code if this is unexpected!",
                },
            )

        profile.hackatime_access_token = access_token
        profile.save()
        return redirect("dashboard")


class LogoutView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        logout(request)
        return redirect("homepage")
