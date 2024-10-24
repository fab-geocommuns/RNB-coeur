from datetime import date

from django.test import TransactionTestCase

from batid.services.imports.import_bdtopo import _known_bdtopo_id
from batid.services.imports.import_bdtopo import bdtopo_recent_release_date
from batid.tests.helpers import create_default_bdg


class ReleaseDate(TransactionTestCase):
    def test(self):

        # Test normal case
        release = bdtopo_recent_release_date(date(2024, 5, 24))
        self.assertEqual(release, "2024-03-15")

        # Test on the day of a new release
        release = bdtopo_recent_release_date(date(2025, 3, 15))
        self.assertEqual(release, "2024-12-15")


class KnownId(TransactionTestCase):
    def setUp(self):

        bdg = create_default_bdg("RNB_ID")
        bdg.add_ext_id("bdtopo", "2024-03-15", "ID", "2024-05-24")
        bdg.save()

        bdg = create_default_bdg("RNB_ID2")
        bdg.add_ext_id("other_source", "2024-03-15", "ID3", "2024-05-24")

        bdg = create_default_bdg("RNB_ID3")
        bdg.add_ext_id("bdtopo", "2024-03-15", "ID5", "2024-05-24")

    def test(self):

        # Simple exist case
        self.assertTrue(_known_bdtopo_id("ID"))

        # Simple not exist case
        self.assertFalse(_known_bdtopo_id("ID2"))

        # There is a bdg with the same ID but it is not a bdtopo ID
        self.assertFalse(_known_bdtopo_id("ID3"))

        # There is a bdg with a bdtopo ID but it is not the same ID
        self.assertFalse(_known_bdtopo_id("ID4"))
