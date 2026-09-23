import hashlib
import hmac
import json
from typing import cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from twisted_site import ari
from twisted_site.models import Profile, Project, ProjectShip

_NOW = 1_700_000_000
_BODY = b'{"event":"review.approved"}'
_DELIVERY_ID = "delivery-123"
_TIMESTAMP = str(_NOW)
_VALID_SIGNATURE = "9128f59fc9af76348b946be25bae8643f76e54f2185e3184e29b0694b630bd23"


def _webhook_signature(body: bytes, timestamp: str, delivery_id: str) -> str:
    message = f"{timestamp}.{delivery_id}.".encode() + body
    return hmac.new(b"outbound-secret", message, hashlib.sha256).hexdigest()


class WebhookSignatureTests(SimpleTestCase):
    def test_accepts_a_known_valid_signature(self) -> None:
        with (
            patch("twisted_site.ari.ARI_WEBHOOK_SECRET", "webhook-secret"),
            patch("twisted_site.ari.time.time", return_value=_NOW),
        ):
            verified = ari.verify_webhook_signature(
                _BODY,
                _TIMESTAMP,
                _DELIVERY_ID,
                _VALID_SIGNATURE,
            )

        self.assertTrue(verified)

    def test_rejects_missing_headers(self) -> None:
        with patch("twisted_site.ari.time.time", return_value=_NOW):
            invalid_header_sets = (
                ("", _DELIVERY_ID, _VALID_SIGNATURE),
                (_TIMESTAMP, "", _VALID_SIGNATURE),
                (_TIMESTAMP, _DELIVERY_ID, ""),
            )
            for timestamp, delivery_id, signature in invalid_header_sets:
                with self.subTest(
                    timestamp=timestamp,
                    delivery_id=delivery_id,
                    signature=signature,
                ):
                    self.assertFalse(
                        ari.verify_webhook_signature(
                            _BODY,
                            timestamp,
                            delivery_id,
                            signature,
                        ),
                    )

    def test_rejects_malformed_and_out_of_window_timestamps(self) -> None:
        invalid_timestamps = (
            "not-a-timestamp",
            str(_NOW - ari.WEBHOOK_MAX_AGE_SECONDS - 1),
            str(_NOW + ari.WEBHOOK_MAX_AGE_SECONDS + 1),
        )
        with (
            patch("twisted_site.ari.ARI_WEBHOOK_SECRET", "webhook-secret"),
            patch("twisted_site.ari.time.time", return_value=_NOW),
        ):
            for timestamp in invalid_timestamps:
                with self.subTest(timestamp=timestamp):
                    self.assertFalse(
                        ari.verify_webhook_signature(
                            _BODY,
                            timestamp,
                            _DELIVERY_ID,
                            _VALID_SIGNATURE,
                        ),
                    )

    def test_accepts_timestamp_at_age_boundary(self) -> None:
        timestamp = str(_NOW - ari.WEBHOOK_MAX_AGE_SECONDS)
        signature = "10767111eece116701615f8c1fe3ef87427b3684424c8a23b4926e3900653f7d"
        with (
            patch("twisted_site.ari.ARI_WEBHOOK_SECRET", "webhook-secret"),
            patch("twisted_site.ari.time.time", return_value=_NOW),
        ):
            verified = ari.verify_webhook_signature(
                _BODY,
                timestamp,
                _DELIVERY_ID,
                signature,
            )

        self.assertTrue(verified)

    def test_rejects_tampered_delivery(self) -> None:
        with (
            patch("twisted_site.ari.ARI_WEBHOOK_SECRET", "webhook-secret"),
            patch("twisted_site.ari.time.time", return_value=_NOW),
        ):
            self.assertFalse(
                ari.verify_webhook_signature(
                    b'{"event":"review.rejected"}',
                    _TIMESTAMP,
                    _DELIVERY_ID,
                    _VALID_SIGNATURE,
                ),
            )
            self.assertFalse(
                ari.verify_webhook_signature(
                    _BODY,
                    _TIMESTAMP,
                    "different-delivery",
                    _VALID_SIGNATURE,
                ),
            )
            self.assertFalse(
                ari.verify_webhook_signature(
                    _BODY,
                    _TIMESTAMP,
                    _DELIVERY_ID,
                    "0" * 64,
                ),
            )


class AriSigningTests(SimpleTestCase):
    def test_signs_string_and_bytes_identically(self) -> None:
        with patch("twisted_site.ari.ARI_SIGNING_SECRET", "outbound-secret"):
            signature = ari.get_hex_signature(_BODY)
            string_signature = ari.get_hex_signature(_BODY.decode())

        self.assertEqual(
            signature,
            "1fb64affceaf4584e40493f64f460edfbde1b1fa9133898b647cc0c62465dd09",
        )
        self.assertEqual(string_signature, signature)


class AriStatusTests(SimpleTestCase):
    def test_maps_review_phases_and_decisions_to_display_status(self) -> None:
        cases: tuple[tuple[dict[str, str] | None, tuple[str, str]], ...] = (
            (None, ("pending", "pending")),
            ({}, ("pending", "pending")),
            ({"phase": "processing"}, ("pending", "pending")),
            (
                {"phase": "second_pass", "decision": "changes"},
                ("requested_changes", "pending"),
            ),
            (
                {"phase": "reviewed", "decision": "approved"},
                ("approved", "approved"),
            ),
            (
                {"phase": "reviewed", "decision": "rejected"},
                ("rejected", "rejected"),
            ),
            ({"phase": "withdrawn"}, ("rejected", "rejected")),
            (
                {"phase": "reviewed", "decision": "unknown"},
                ("pending", "pending"),
            ),
        )
        for status, expected in cases:
            with self.subTest(status=status):
                self.assertEqual(ari.ship_passes_from_status(status), expected)


class AriWebhookTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    ship: ProjectShip  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="maker")
        self.profile = Profile.objects.create(user=self.user, slack_id="U-MAKER")
        self.project = Project.objects.create(
            user=self.user,
            project_name="Test Project",
            project_description="Description",
            project_type="software",
        )
        self.ship = ProjectShip.objects.create(project=self.project)

    def post_webhook(self, payload: dict[str, object]) -> HttpResponse:
        body = json.dumps(payload).encode()
        timestamp = str(_NOW)
        delivery_id = "delivery-webhook-test"
        expected_signature = _webhook_signature(body, timestamp, delivery_id)
        with (
            patch("twisted_site.ari.ARI_SIGNING_SECRET", "outbound-secret"),
            patch("twisted_site.ari.ARI_WEBHOOK_SECRET", "outbound-secret"),
            patch("twisted_site.ari.time.time", return_value=_NOW),
        ):
            return cast(
                "HttpResponse",
                cast(
                    "object",
                    self.client.post(
                        reverse("ari"),
                        data=body,
                        content_type="application/json",
                        headers={
                            "X-Ari-Timestamp": timestamp,
                            "X-Ari-Delivery-Id": delivery_id,
                            "X-Ari-Signature": expected_signature,
                        },
                    ),
                ),
            )

    def test_rejects_invalid_signature_without_changing_ship(self) -> None:
        with (
            patch("twisted_site.ari.ARI_WEBHOOK_SECRET", "outbound-secret"),
            patch("twisted_site.ari.time.time", return_value=_NOW),
        ):
            response = self.client.post(
                reverse("ari"),
                data=json.dumps(
                    {
                        "external_id": f"twisted-{self.project.pk}",
                        "event": "review.approved",
                    },
                ),
                content_type="application/json",
                headers={
                    "X-Ari-Timestamp": str(_NOW),
                    "X-Ari-Delivery-Id": "delivery-invalid",
                    "X-Ari-Signature": "0" * 64,
                },
            )

        self.assertEqual(response.status_code, 401)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.status, "pending")

    def test_approved_event_updates_ship_and_notifies_maker(self) -> None:
        payload: dict[str, object] = {
            "external_id": f"twisted-{self.project.pk}",
            "event": "review.approved",
            "review": {
                "note_to_maker": "Nice work",
                "audit_note": "Verified",
                "justification": {
                    "technical_features": "Canvas",
                    "deflation_reason": "None",
                },
            },
        }
        with patch("twisted_site.views.ari.send_blocks") as send_blocks:
            response = self.post_webhook(payload)

        self.assertEqual(response.status_code, 200)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.status, "approved")
        self.assertEqual(self.ship.note_to_maker, "Nice work")
        self.assertEqual(self.ship.audit_note, "Verified")
        self.assertEqual(self.ship.technical_features, "Canvas")
        self.assertEqual(self.ship.deflation_reason, "None")
        send_blocks.assert_called_once()

    def test_review_changes_ignores_mismatched_decision(self) -> None:
        with patch("twisted_site.views.ari.send_blocks") as send_blocks:
            response = self.post_webhook(
                {
                    "external_id": f"twisted-{self.project.pk}",
                    "event": "review.changes",
                    "decision": "approved",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.status, "pending")
        send_blocks.assert_not_called()

    def test_unknown_event_is_ignored(self) -> None:
        with patch("twisted_site.views.ari.send_blocks") as send_blocks:
            response = self.post_webhook(
                {
                    "external_id": f"twisted-{self.project.pk}",
                    "event": "review.unknown",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.status, "pending")
        send_blocks.assert_not_called()
