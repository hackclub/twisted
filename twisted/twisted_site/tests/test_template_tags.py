from django.test import SimpleTestCase

from twisted_site.templatetags.maths import divide
from twisted_site.templatetags.time_filters import minutes_to_hours_minutes


class TemplateTagTests(SimpleTestCase):
    def test_minutes_to_hours_minutes_formats_boundaries(self) -> None:
        cases = (
            (0, "0m"),
            (1, "1m"),
            (59, "59m"),
            (60, "1h"),
            (61, "1h 1m"),
            (125, "2h 5m"),
            ("90", "1h 30m"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(minutes_to_hours_minutes(value), expected)

    def test_minutes_filter_preserves_invalid_values(self) -> None:
        self.assertEqual(minutes_to_hours_minutes("invalid"), "invalid")
        self.assertIsNone(minutes_to_hours_minutes(None))

    def test_divide_returns_float_ratio(self) -> None:
        self.assertEqual(divide(3.0, 2.0), 1.5)
        self.assertEqual(divide(0.0, 2.0), 0.0)

    def test_divide_by_zero_raises(self) -> None:
        with self.assertRaises(ZeroDivisionError):
            _ = divide(1.0, 0.0)
