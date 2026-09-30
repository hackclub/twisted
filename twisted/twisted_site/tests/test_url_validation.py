from django.test import SimpleTestCase

from twisted_site.validation import invalid_http_urls, is_http_url, sanitize_http_url


class HttpUrlValidationTests(SimpleTestCase):
    def test_accepts_absolute_http_and_https_urls(self) -> None:
        valid_urls = (
            "http://example.com",
            "https://example.com",
            "https://example.com/path?query=1#fragment",
            "HTTPS://EXAMPLE.COM",
            "https://sub.example.com:8443/path",
        )
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(is_http_url(url))

    def test_rejects_non_http_schemes(self) -> None:
        invalid_urls = (
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
            "file:///etc/passwd",
            "ftp://example.com/file",
            "//example.com/path",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(is_http_url(url))

    def test_rejects_empty_values_and_missing_hosts(self) -> None:
        invalid_urls = ("", "http://", "https:///path", "http://:8000")
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(is_http_url(url))

    def test_sanitize_trims_valid_urls_and_blanks_invalid_values(self) -> None:
        self.assertEqual(
            sanitize_http_url(" https://example.com/page "),
            "https://example.com/page",
        )
        self.assertEqual(sanitize_http_url("javascript:alert(1)"), "")
        self.assertEqual(sanitize_http_url("   "), "")
        self.assertEqual(sanitize_http_url(None), "")
        self.assertEqual(sanitize_http_url(123), "")

    def test_invalid_http_urls_reports_only_broken_non_empty_values(self) -> None:
        values = {
            "repo_url": "https://github.com/example/repo",
            "playable_url": "javascript:alert(1)",
            "screenshot_url": "",
        }

        self.assertEqual(invalid_http_urls(values), ["playable_url"])
