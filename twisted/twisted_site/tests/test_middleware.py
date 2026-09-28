from typing import override

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone
from mysite.middleware import TimezoneMiddleware


class TimezoneMiddlewareTests(SimpleTestCase):
    factory: RequestFactory  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override
    def tearDown(self) -> None:
        timezone.deactivate()

    def test_valid_cookie_activates_timezone_during_request(self) -> None:
        request = self.factory.get("/", headers={"cookie": "django_timezone=America/New_York"})
        expected_response = HttpResponse("ok")

        def get_response(_request: HttpRequest) -> HttpResponse:
            self.assertEqual(timezone.get_current_timezone_name(), "America/New_York")
            return expected_response

        response = TimezoneMiddleware(get_response)(request)

        self.assertIs(response, expected_response)

    def test_missing_cookie_deactivates_timezone(self) -> None:
        request = self.factory.get("/")
        expected_response = HttpResponse("ok")

        def get_response(_request: HttpRequest) -> HttpResponse:
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")
            return expected_response

        response = TimezoneMiddleware(get_response)(request)

        self.assertIs(response, expected_response)

    def test_invalid_cookie_is_logged_and_ignored(self) -> None:
        request = self.factory.get("/", headers={"cookie": "django_timezone=Not/AZone"})
        expected_response = HttpResponse("ok")

        def get_response(_request: HttpRequest) -> HttpResponse:
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")
            return expected_response

        with self.assertLogs("mysite.middleware", level="WARNING") as logs:
            response = TimezoneMiddleware(get_response)(request)

        self.assertIs(response, expected_response)
        self.assertIn("Invalid django_timezone cookie value", logs.output[0])
