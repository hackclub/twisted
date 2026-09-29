import os
from typing import cast, override
from unittest.mock import patch

from authlib.integrations.base_client import (  # pyrefly: ignore[untyped-import]
    MismatchingStateError,
)
from authlib.integrations.base_client.errors import (  # pyrefly: ignore[untyped-import]
    OAuthError,
)
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from twisted_site.models import Profile
from twisted_site.views.client.auth import _default_avatar_url


class HCAIdentityCallbackTests(TestCase):
    @override
    def setUp(self) -> None:
        self.client = Client()

    def token(self, *, slack_id: str = "U-MAKER") -> dict[str, object]:
        return {
            "access_token": "hca-access-token",
            "userinfo": {
                "sub": "hca!maker",
                "email": "maker@example.com",
                "name": "Maker Name",
                "given_name": "Maker",
                "family_name": "Name",
                "slack_id": slack_id,
                "verification_status": "verified",
                "ysws_eligible": True,
            },
        }

    def slack_user(self) -> dict[str, object]:
        return {
            "user": {
                "profile": {
                    "display_name": "Maker",
                    "image_512": "https://example.com/avatar.png",
                },
            },
        }

    def test_successful_callback_creates_user_profile_and_starts_hackatime_login(self) -> None:
        referrer = Profile.objects.create(
            user=User.objects.create_user(username="referrer"),
            my_referral_code="REFER",
        )
        self.client.cookies["referral"] = "REFER"
        with (
            patch(
                "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
                return_value=self.token(),
            ),
            patch(
                "twisted_site.views.client.auth.slack_bot.users_info",
                return_value=self.slack_user(),
            ),
            patch(
                "twisted_site.views.client.auth.secrets.token_urlsafe",
                return_value="generated-state",
            ),
            patch("twisted_site.views.client.auth.log_to_channel"),
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://hackatime.hackclub.com/oauth/authorize?", response["Location"])
        self.assertIn("state=generated-state", response["Location"])
        user = User.objects.get(username="hca_maker")
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.slack_id, "U-MAKER")
        self.assertEqual(profile.hca_access_token, "hca-access-token")
        self.assertEqual(profile.hackatime_state, "generated-state")
        self.assertEqual(profile.referred_by, referrer)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_missing_linked_slack_id_rejects_identity(self) -> None:
        with patch(
            "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
            return_value=self.token(slack_id=""),
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_login_disabled_rejects_callback_before_oauth_exchange(self) -> None:
        with (
            patch.dict(os.environ, {"LOGIN_ENABLED": "false"}),
            patch("twisted_site.views.client.auth.oauth.hca.authorize_access_token") as exchange,
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 200)
        exchange.assert_not_called()

    def test_maybe_login_mode_rejects_unapproved_user(self) -> None:
        with (
            patch.dict(os.environ, {"LOGIN_ENABLED": "maybe"}),
            patch(
                "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
                return_value=self.token(),
            ),
            patch(
                "twisted_site.views.client.auth.slack_bot.users_info",
                return_value=self.slack_user(),
            ),
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Profile.objects.filter(user__username="hca_maker").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_oauth_state_mismatch_is_rejected(self) -> None:
        with patch(
            "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
            side_effect=MismatchingStateError(),
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_oauth_error_is_reported_gracefully(self) -> None:
        with patch(
            "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
            side_effect=OAuthError("invalid_grant"),
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_missing_subject_is_rejected(self) -> None:
        token = self.token()
        userinfo = cast("dict[str, object]", token["userinfo"])
        _ = userinfo.pop("sub")

        with patch(
            "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
            return_value=token,
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_missing_access_token_is_rejected(self) -> None:
        token = self.token()
        _ = token.pop("access_token")

        with patch(
            "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
            return_value=token,
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_slack_lookup_failure_uses_identity_fallback(self) -> None:
        with (
            patch(
                "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
                return_value=self.token(),
            ),
            patch(
                "twisted_site.views.client.auth.slack_bot.users_info",
                side_effect=RuntimeError("Slack unavailable"),
            ),
            patch(
                "twisted_site.views.client.auth.secrets.token_urlsafe",
                return_value="generated-state",
            ),
            patch("twisted_site.views.client.auth.log_to_channel"),
            self.assertLogs("twisted_site.views.client.auth", level="ERROR"),
        ):
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(user__username="hca_maker")
        self.assertEqual(profile.slack_username, "Maker Name")
        self.assertEqual(profile.slack_pfp_url, "https://example.invalid/avatar.png")

    def test_slack_failure_without_configured_pfp_uses_static_avatar(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "twisted_site.views.client.auth.oauth.hca.authorize_access_token",
                return_value=self.token(),
            ),
            patch(
                "twisted_site.views.client.auth.slack_bot.users_info",
                side_effect=RuntimeError("Slack unavailable"),
            ),
            patch(
                "twisted_site.views.client.auth.secrets.token_urlsafe",
                return_value="generated-state",
            ),
            patch("twisted_site.views.client.auth.log_to_channel"),
            self.assertLogs("twisted_site.views.client.auth", level="ERROR"),
        ):
            _ = os.environ.pop("DEFAULT_PFP", None)
            response = self.client.get(reverse("auth_callback"))

        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(user__username="hca_maker")
        self.assertEqual(
            profile.slack_pfp_url,
            f"{settings.STATIC_URL}images/twisted_t.png",
        )


class DefaultAvatarTests(SimpleTestCase):
    def test_configured_default_pfp_wins(self) -> None:
        with patch.dict(os.environ, {"DEFAULT_PFP": "https://example.com/pfp.png"}):
            self.assertEqual(_default_avatar_url(), "https://example.com/pfp.png")

    def test_static_asset_is_used_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            _ = os.environ.pop("DEFAULT_PFP", None)
            self.assertEqual(
                _default_avatar_url(),
                f"{settings.STATIC_URL}images/twisted_t.png",
            )


class LoginLogoutTests(TestCase):
    def test_existing_hackatime_user_is_redirected_away_from_login(self) -> None:
        user = User.objects.create_user(username="linked")
        _ = Profile.objects.create(user=user, hackatime_access_token="token")
        client = Client()
        client.force_login(user)

        response = client.post(reverse("login"))

        self.assertRedirects(response, reverse("dashboard"))

    def test_login_delegates_to_hca_authorize_redirect(self) -> None:
        client = Client()
        response_value = HttpResponseRedirect("https://identity.example/authorize")
        with patch(
            "twisted_site.views.client.auth.oauth.hca.authorize_redirect",
            return_value=response_value,
        ) as authorize_redirect:
            response = client.post(reverse("login"))

        self.assertEqual(response, response_value)
        authorize_redirect.assert_called_once()

    def test_logout_clears_authenticated_session(self) -> None:
        user = User.objects.create_user(username="logout")
        _ = Profile.objects.create(user=user)
        client = Client()
        client.force_login(user)

        response = client.post(reverse("logout"))

        self.assertRedirects(response, reverse("homepage"))
        self.assertNotIn("_auth_user_id", client.session)
