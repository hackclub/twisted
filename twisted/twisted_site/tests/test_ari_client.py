import hashlib
import hmac
from typing import TYPE_CHECKING, cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from twisted_site import ari
from twisted_site.models import Journal, Profile, Project, ProjectShip

if TYPE_CHECKING:
    import requests


class _Response:
    content = b"{}"

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, str]:
        return {"phase": "reviewed", "decision": "approved"}


class AriRequestTests(SimpleTestCase):
    def test_post_request_jsonifies_and_signs_payload(self) -> None:
        response = cast("requests.Response", cast("object", _Response()))
        with (
            patch("twisted_site.ari.ARI_INGEST_ENDPOINT", "https://ari.example/"),
            patch("twisted_site.ari.ARI_SIGNING_SECRET", "outbound-secret"),
            patch("twisted_site.ari.requests.request", return_value=response) as request,
        ):
            result = ari.send_request("POST", {"hello": "world"}, "/submit")

        self.assertIs(result, response)
        data = b'{"hello": "world"}'
        expected_signature = hmac.new(b"outbound-secret", data, hashlib.sha256).hexdigest()
        request.assert_called_once_with(
            "POST",
            "https://ari.example/submit",
            data=data,
            headers={
                "X-Ari-Signature": expected_signature,
                "Content-Type": "application/json",
            },
            timeout=10,
        )

    def test_get_request_uses_bearer_authorization(self) -> None:
        response = cast("requests.Response", cast("object", _Response()))
        with (
            patch("twisted_site.ari.ARI_INGEST_ENDPOINT", "https://ari.example/"),
            patch("twisted_site.ari.ARI_SIGNING_SECRET", "outbound-secret"),
            patch("twisted_site.ari.requests.request", return_value=response) as request,
        ):
            _ = ari.send_request("GET", endpoint="/status?external_id=twisted-1")

        request.assert_called_once_with(
            "GET",
            "https://ari.example/status?external_id=twisted-1",
            data=None,
            headers={"Authorization": "Bearer outbound-secret"},
            timeout=10,
        )

    def test_get_project_status_returns_parsed_response(self) -> None:
        project = Project(pk=42)
        response = cast("requests.Response", cast("object", _Response()))
        with patch("twisted_site.ari.send_request", return_value=response):
            status = ari.get_project_status(project)

        self.assertEqual(status, {"phase": "reviewed", "decision": "approved"})


class AriSendShipTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    ship: ProjectShip  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="ari-maker", email="maker@example.com")
        self.profile = Profile.objects.create(
            user=self.user,
            slack_id="U-MAKER",
            slack_username="Maker",
        )
        self.project = Project.objects.create(
            user=self.user,
            project_name="Outbound project",
            project_description="Description",
            project_type="hardware",
            repo_url="https://github.com/example/repo",
            playable_url="https://example.com/play",
            screenshot_url="https://example.com/image.png",
            hackatime_project_names=["Hackatime project"],
        )
        _ = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Journal",
            minutes_worked=30,
            reduced_minutes=20,
        )
        self.ship = ProjectShip.objects.create(project=self.project)

    def test_send_ship_includes_project_evidence_payload(self) -> None:
        response = cast("requests.Response", cast("object", _Response()))
        with patch("twisted_site.ari.send_request", return_value=response) as send_request:
            ari.send_ship(self.ship)

        method = cast("str", send_request.call_args.args[0])
        payload = cast("dict[str, object]", send_request.call_args.args[1])
        self.assertEqual(method, "POST")
        self.assertEqual(payload["external_id"], f"twisted-{self.project.pk}")
        self.assertEqual(payload["title"], "Outbound project")
        self.assertEqual(payload["track"], "hardware")
        self.assertEqual(payload["repo_url"], "https://github.com/example/repo")
        self.assertEqual(payload["hackatime_projects"], ["Hackatime project"])
        journals = cast("list[dict[str, str | int]]", payload["journals"])
        self.assertEqual(journals[0]["minutes"], 20)

    @override_settings(DEBUG_REVIEW=True)
    def test_debug_review_skips_outbound_delivery(self) -> None:
        with patch("twisted_site.ari.send_request") as send_request:
            ari.send_ship(self.ship)

        send_request.assert_not_called()
