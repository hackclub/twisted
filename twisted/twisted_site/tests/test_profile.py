from datetime import timedelta
from typing import override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from requests import Timeout

from twisted_site.hca import Address, Identity
from twisted_site.models import Profile


class ProfileCountryTests(TestCase):
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        user = User.objects.create_user(username="country-user")
        self.profile = Profile.objects.create(user=user, hca_access_token="token")

    def identity(self, country: str | None) -> Identity:
        primary_address = (
            Address(
                id="primary",
                first_name="Maker",
                last_name="Name",
                line_1="",
                line_2="",
                city="",
                state="",
                postal_code="",
                country=country,
                phone_number="",
                primary=True,
            )
            if country is not None
            else None
        )
        return Identity(
            id="identity",
            ysws_eligible=True,
            verification_status="verified",
            first_name="Maker",
            last_name="Name",
            primary_email="maker@example.com",
            slack_id="U-MAKER",
            phone_number="",
            birthday="2008-01-01",
            addresses=[primary_address] if primary_address is not None else [],
            primary_address=primary_address,
        )

    def test_cached_country_avoids_external_request(self) -> None:
        self.profile.country = "CA"
        self.profile.country_cached_until = timezone.now() + timedelta(hours=1)
        self.profile.save()

        with patch("twisted_site.models.hca.get_user_data") as get_user_data:
            country = self.profile.get_country()

        self.assertEqual(country, "CA")
        get_user_data.assert_not_called()

    def test_expired_cache_refreshes_primary_country(self) -> None:
        self.profile.country = "Old"
        self.profile.country_cached_until = timezone.now() - timedelta(seconds=1)
        self.profile.save()

        with patch(
            "twisted_site.models.hca.get_user_data",
            return_value=self.identity("US"),
        ) as get_user_data:
            country = self.profile.get_country()

        self.assertEqual(country, "US")
        get_user_data.assert_called_once_with("token")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.country, "US")
        self.assertGreater(self.profile.country_cached_until, timezone.now())

    def test_missing_primary_address_returns_unknown(self) -> None:
        with patch(
            "twisted_site.models.hca.get_user_data",
            return_value=self.identity(None),
        ):
            country = self.profile.get_country()

        self.assertEqual(country, "Unknown")

    def test_network_timeout_is_cached_as_unknown(self) -> None:
        with patch(
            "twisted_site.models.hca.get_user_data",
            side_effect=Timeout("HCA timed out"),
        ):
            country = self.profile.get_country()

        self.assertEqual(country, "Unknown")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.country, "Unknown")
        self.assertIsNotNone(self.profile.country_cached_until)
