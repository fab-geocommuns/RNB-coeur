from datetime import date
from unittest import mock

from batid.models import Building
from batid.services.imports.import_bdtopo import (
    _known_bdtopo_id,
    bdtopo_recente_release_date,
)
from batid.services.tchap import TchapLevel
from batid.tasks import queue_full_bdtopo_import
from batid.tests.helpers import create_default_bdg
from django.test import SimpleTestCase, TransactionTestCase


class ReleaseDate(TransactionTestCase):
    def test(self):

        # Test normal case
        release = bdtopo_recente_release_date(date(2024, 5, 24))
        self.assertEqual(release, "2024-03-15")

        # Test on the day of a new release
        release = bdtopo_recente_release_date(date(2025, 3, 15))
        self.assertEqual(release, "2024-12-15")


class QueueFullImportMessage(SimpleTestCase):
    @mock.patch("batid.tasks.create_bdtopo_full_import_tasks", return_value=[])
    @mock.patch("batid.tasks.notify_tech")
    def test_bdtopo_message_shows_picked_release(self, notify_mock, create_mock):
        """
        Input: queue_full_bdtopo_import for departement "01" with
        released_before="2026-10-01".
        Expected: one launch message with the departements and the release actually
        picked (2026-09-15) shown as "15/09/2026", not the released_before bound.
        """
        queue_full_bdtopo_import.run(
            dpt_start="01", dpt_end="01", released_before="2026-10-01"
        )

        notify_mock.assert_called_once_with(
            level=TchapLevel.LAUNCH,
            title="Import BD Topo lancé",
            details=[("Départements", "01 à 01"), ("Millésime", "15/09/2026")],
        )


class KnownId(TransactionTestCase):
    def setUp(self):

        bdg = create_default_bdg("RNB_ID")
        bdg.ext_ids = Building.add_ext_id(
            [], "bdtopo", "2024-03-15", "ID", "2024-05-24"
        )
        bdg.save()

        bdg = create_default_bdg("RNB_ID2")
        bdg.ext_ids = Building.add_ext_id(
            [], "other_source", "2024-03-15", "ID3", "2024-05-24"
        )
        bdg.save()

        bdg = create_default_bdg("RNB_ID3")
        bdg.ext_ids = Building.add_ext_id(
            [], "bdtopo", "2024-03-15", "ID5", "2024-05-24"
        )
        bdg.save()

    def test(self):

        # Simple exist case
        self.assertTrue(_known_bdtopo_id("ID"))

        # Simple not exist case
        self.assertFalse(_known_bdtopo_id("ID2"))

        # There is a bdg with the same ID but it is not a bdtopo ID
        self.assertFalse(_known_bdtopo_id("ID3"))

        # There is a bdg with a bdtopo ID but it is not the same ID
        self.assertFalse(_known_bdtopo_id("ID4"))
