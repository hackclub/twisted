from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch

from django.test import SimpleTestCase
from requests import HTTPError

from twisted_site import hackatime, hca


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return self.payload


class HackatimeClientTests(SimpleTestCase):
    def test_authhelper_merges_headers_with_bearer_token(self) -> None:
        self.assertEqual(
            hackatime.authhelper("token"),
            {"Authorization": "Bearer token"},
        )
        self.assertEqual(
            hackatime.authhelper("token", {"X-Test": "value"}),
            {"Authorization": "Bearer token", "X-Test": "value"},
        )
        self.assertEqual(
            hackatime.authhelper("token", {"Authorization": "Custom"}),
            {"Authorization": "Custom"},
        )

    def test_me_parses_authenticated_identity(self) -> None:
        response = _Response(
            {
                "id": 42,
                "emails": ["maker@example.com"],
                "slack_id": "U-MAKER",
                "github_username": "maker",
                "trust_factor": {
                    "trust_level": "trusted",
                    "trust_value": 0.75,
                },
            },
        )
        with patch("twisted_site.hackatime.requests.get", return_value=response) as get:
            identity = hackatime.me("token")

        get.assert_called_once_with(
            "https://hackatime.hackclub.com/api/v1/authenticated/me",
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )
        self.assertEqual(identity.id, 42)
        self.assertEqual(identity.slack_id, "U-MAKER")
        self.assertEqual(identity.trust_level, "trusted")
        self.assertEqual(identity.trust_value, 0.75)

    def test_projects_sends_filters_and_parses_heartbeat(self) -> None:
        response = _Response(
            {
                "projects": [
                    {
                        "name": "Example",
                        "total_seconds": 3600,
                        "most_recent_heartbeat": "2026-01-01T12:00:00+00:00",
                        "languages": ["Python"],
                    },
                ],
            },
        )
        with patch("twisted_site.hackatime.requests.get", return_value=response) as get:
            projects = hackatime.projects(
                "token",
                include_archived=True,
                start=datetime(2026, 1, 1, tzinfo=UTC),
                projects=["Example", "Other"],
            )

        get.assert_called_once_with(
            "https://hackatime.hackclub.com/api/v1/authenticated/projects",
            params={
                "include_archived": "true",
                "start": "2026-01-01T00:00:00+00:00",
                "projects": "Example,Other",
            },
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )
        self.assertEqual(projects[0].name, "Example")
        self.assertEqual(projects[0].total_seconds, 3600)
        self.assertEqual(projects[0].languages, ["Python"])

    def test_http_errors_are_propagated(self) -> None:
        with (
            patch(
                "twisted_site.hackatime.requests.get",
                side_effect=HTTPError("unavailable"),
            ),
            self.assertRaises(HTTPError),
        ):
            _ = hackatime.me("token")


class HCAClientTests(SimpleTestCase):
    def identity_payload(self) -> dict[str, object]:
        return {
            "identity": {
                "id": "identity-1",
                "ysws_eligible": True,
                "verification_status": "verified",
                "first_name": "Maker",
                "primary_email": "maker@example.com",
                "slack_id": "U-MAKER",
                "phone_number": "",
                "birthday": "2008-01-01",
                "addresses": [
                    {
                        "id": "secondary",
                        "primary": False,
                        "country": "CA",
                    },
                    {
                        "id": "primary",
                        "primary": True,
                        "country": "US",
                    },
                ],
            },
        }

    def test_auth_headers_include_bearer_token(self) -> None:
        self.assertEqual(
            hca.get_auth_headers("token"),
            {"Authorization": "Bearer token"},
        )
        self.assertEqual(
            hca.get_auth_headers("token", {"X-Test": "value"}),
            {"Authorization": "Bearer token", "X-Test": "value"},
        )

    def test_get_user_data_selects_primary_address(self) -> None:
        response = _Response(self.identity_payload())
        with patch("twisted_site.hca.requests.get", return_value=response) as get:
            identity = hca.get_user_data("token")

        get.assert_called_once_with(
            "https://auth.hackclub.com/api/v1/me",
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )
        self.assertEqual(identity.id, "identity-1")
        self.assertTrue(identity.ysws_eligible)
        self.assertEqual(len(identity.addresses), 2)
        primary_address = identity.primary_address
        if primary_address is None:
            self.fail("Expected a primary address")
        self.assertEqual(primary_address.id, "primary")
        self.assertEqual(primary_address.country, "US")

    def test_identity_without_addresses_is_supported(self) -> None:
        payload = self.identity_payload()
        identity_payload = cast("dict[str, object]", payload["identity"])
        empty_addresses: list[dict[str, object]] = []
        identity_payload["addresses"] = empty_addresses
        response = _Response(payload)

        with patch("twisted_site.hca.requests.get", return_value=response):
            identity = hca.get_user_data("token")

        self.assertEqual(identity.addresses, [])
        self.assertIsNone(identity.primary_address)
