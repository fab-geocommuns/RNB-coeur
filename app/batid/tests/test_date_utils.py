import datetime

from batid.utils.date import french_month_year_label, month_bounds, previous_month
from django.test import TestCase
from freezegun import freeze_time


class DateUtilsTestCase(TestCase):
    def test_month_bounds_regular_month(self):
        """
        Input: February 2026.
        Expected: start=2026-02-01 UTC, end=2026-03-01 UTC.
        """
        start, end = month_bounds(2026, 2)
        self.assertEqual(
            start, datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            end, datetime.datetime(2026, 3, 1, tzinfo=datetime.timezone.utc)
        )

    def test_month_bounds_december(self):
        """
        Input: December 2025.
        Expected: start=2025-12-01 UTC, end=2026-01-01 UTC.
        """
        start, end = month_bounds(2025, 12)
        self.assertEqual(
            start, datetime.datetime(2025, 12, 1, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            end, datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        )

    def test_french_month_label(self):
        """
        Input: year=2026, month=2.
        Expected: "février 2026".
        """
        self.assertEqual(french_month_year_label(2026, 2), "février 2026")

    @freeze_time("2026-03-15")
    def test_previous_month_regular(self):
        """
        Input: called on 2026-03-15.
        Expected: returns (2026, 2).
        """
        year, month = previous_month()
        self.assertEqual(year, 2026)
        self.assertEqual(month, 2)

    @freeze_time("2026-01-15")
    def test_previous_month_january(self):
        """
        Input: called on 2026-01-15 (January edge case).
        Expected: returns (2025, 12).
        """
        year, month = previous_month()
        self.assertEqual(year, 2025)
        self.assertEqual(month, 12)
