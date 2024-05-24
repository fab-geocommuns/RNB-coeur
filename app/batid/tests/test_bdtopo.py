from datetime import date

from django.test import TestCase

from batid.services.source import bdtopo_release_before


class BDTopoTestCase(TestCase):

    def test_release_date(self):

        # Test normal case
        release = bdtopo_release_before(date(2024, 5, 24))
        self.assertEqual(release, "2024-03-15")

        # Test on the day of a new release
        release = bdtopo_release_before(date(2025, 3, 15))
        self.assertEqual(release, "2024-12-15")
