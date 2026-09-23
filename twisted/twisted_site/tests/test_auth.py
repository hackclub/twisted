from typing import override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.hackatime import MeResponse
from twisted_site.models import Profile


class _TokenResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, str]:
        return {"access_token": "hackatime-access-token"}


class HackatimeCallbackTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="maker")
        self.profile = Profile.objects.create(
            user=self.user,
            slack_id="U-MAKER",
            hackatime_state="expected-state",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_state_mismatch_is_rejected_and_state_is_cleared(self) -> None:
        response = self.client.get(
            reverse("hackatime_callback"),
            {"state": "wrong-state", "code": "unused-code"},
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.hackatime_state, "")

    def test_anonymous_callback_redirects_to_login(self) -> None:
        self.client.logout()

        response = self.client.get(
            reverse("hackatime_callback"),
            {"state": "expected-state", "code": "authorization-code"},
        )

        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_missing_oauth_parameters_return_bad_request(self) -> None:
        invalid_parameters: tuple[dict[str, str], ...] = (
            {},
            {"state": "expected-state"},
            {"code": "authorization-code"},
        )
        for parameters in invalid_parameters:
            with self.subTest(parameters=parameters):
                response = self.client.get(reverse("hackatime_callback"), parameters)

                self.assertEqual(response.status_code, 400)
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.hackatime_state, "expected-state")

    def test_valid_callback_stores_token_and_cannot_be_replayed(self) -> None:
        me = MeResponse(
            id=123,
            emails=["maker@example.com"],
            slack_id="U-MAKER",
            gh_username="maker",
            trust_level="trusted",
            trust_value=1,
        )
        with (
            patch(
                "twisted_site.views.client.auth.requests.post",
                return_value=_TokenResponse(),
            ) as post_request,
            patch("twisted_site.views.client.auth.hackatime.me", return_value=me) as get_me,
        ):
            response = self.client.get(
                reverse("hackatime_callback"),
                {"state": "expected-state", "code": "authorization-code"},
            )
            replay_response = self.client.get(
                reverse("hackatime_callback"),
                {"state": "expected-state", "code": "authorization-code"},
            )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(replay_response.status_code, 200)
        post_request.assert_called_once_with(
            "https://hackatime.hackclub.com/oauth/token",
            data={
                "client_id": "test-hackatime-client-id",
                "client_secret": "test-hackatime-client-secret",
                "code": "authorization-code",
                "redirect_uri": "http://testserver/oauth/hackatime_callback",
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        get_me.assert_called_once_with("hackatime-access-token")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.hackatime_access_token, "hackatime-access-token")
        self.assertEqual(self.profile.hackatime_state, "")

    def test_slack_mismatch_does_not_store_access_token(self) -> None:
        me = MeResponse(
            id=123,
            emails=["maker@example.com"],
            slack_id="U-DIFFERENT",
            gh_username="maker",
            trust_level="trusted",
            trust_value=1,
        )
        with (
            patch(
                "twisted_site.views.client.auth.requests.post",
                return_value=_TokenResponse(),
            ),
            patch("twisted_site.views.client.auth.hackatime.me", return_value=me),
        ):
            response = self.client.get(
                reverse("hackatime_callback"),
                {"state": "expected-state", "code": "authorization-code"},
            )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.hackatime_access_token, "")
        self.assertEqual(self.profile.hackatime_state, "")
