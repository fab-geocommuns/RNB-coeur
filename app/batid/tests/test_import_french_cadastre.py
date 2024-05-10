from datetime import date

from django.test import TestCase

from batid.services.source import french_cadastre_most_recent_release_date


class ImportFrenchCadastreTestCase(TestCase):

    def test_realease_dates(self):

        before = date(2024, 4, 30)
        realease = french_cadastre_most_recent_release_date(before)
        expected = "2024-04-01"
        self.assertEqual(realease, expected)

        before = date(2025, 1, 1)
        realease = french_cadastre_most_recent_release_date(before)
        expected = "2025-01-01"
        self.assertEqual(realease, expected)
