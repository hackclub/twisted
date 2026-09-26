from typing import cast

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase

from twisted_site.models import Profile


class TestSettingsTests(SimpleTestCase):
    def test_uses_safe_isolated_settings(self) -> None:
        self.assertFalse(settings.DEBUG)
        self.assertFalse(settings.DEBUG_REVIEW)
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        storages = cast("dict[str, dict[str, str]]", settings.STORAGES)
        self.assertEqual(
            storages["staticfiles"]["BACKEND"],
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )


class HealthEndpointTests(SimpleTestCase):
    def test_health_endpoints_return_no_content(self) -> None:
        for path in ("/health", "/health/"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 204)
                self.assertEqual(response.content, b"")


class DatabaseHarnessTests(TestCase):
    def test_postgres_migrations_create_application_tables(self) -> None:
        self.assertEqual(connection.vendor, "postgresql")
        self.assertEqual(Profile.objects.count(), 0)
