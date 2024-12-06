from datetime import date

from django.test import TestCase

from batid.services.imports.import_plots import etalab_recent_release_date


class ReleaseDate(TestCase):
    def test(self):

        # Test normal case
        release = etalab_recent_release_date(date(2025, 5, 24))
        self.assertEqual(release, "2025-04-01")

        # Test on the day of a new release
        release = etalab_recent_release_date(date(2025, 7, 1))
        self.assertEqual(release, "2024-04-01")
