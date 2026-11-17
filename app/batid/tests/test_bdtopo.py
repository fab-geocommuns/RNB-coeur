from datetime import date
from unittest import mock

from batid.models import Building, BuildingImport
from batid.services.imports.import_bdtopo import (
    _known_bdtopo_id,
    bdtopo_recente_release_date,
)
from batid.services.tchap import Code, TchapLevel
from batid.tasks import queue_full_bdtopo_import, report_bdtopo_import
from batid.tests.helpers import create_default_bdg
from django.test import SimpleTestCase, TestCase, TransactionTestCase


class ReleaseDate(TransactionTestCase):
    def test(self):

        # Test normal case
        release = bdtopo_recente_release_date(date(2024, 5, 24))
        self.assertEqual(release, "2024-03-15")

        # Test on the day of a new release
        release = bdtopo_recente_release_date(date(2025, 3, 15))
        self.assertEqual(release, "2024-12-15")


class QueueFullImportMessage(SimpleTestCase):
    @mock.patch("batid.tasks.create_bdtopo_full_import_tasks")
    @mock.patch("batid.tasks.notify_tech")
    def test_bdtopo_message_shows_picked_release(self, notify_mock, create_mock):
        """
        Input: queue_full_bdtopo_import for departement "01" with
        released_before="2026-10-01".
        Expected: one launch message with the departements and the release actually
        picked (2026-09-15) shown as "15/09/2026", not the released_before bound;
        the import chord is queued once.
        """
        queue_full_bdtopo_import.run(
            dpt_start="01", dpt_end="01", released_before="2026-10-01"
        )

        notify_mock.assert_called_once_with(
            level=TchapLevel.LAUNCH,
            title="Import BD Topo lancé",
            details=[("Départements", "01 à 01"), ("Millésime", "15/09/2026")],
        )
        create_mock.return_value.apply_async.assert_called_once_with()


class ReportBDTopoImport(TestCase):
    @mock.patch("batid.tasks.notify_tech")
    def test_summary(self, notify_mock):
        """
        Input: a launch of 3 departments that skipped 3, 0 and 2 features, with two
        import rows of 10 and 5 candidates, and one row of another launch.
        Expected: one success message "Import BD Topo terminé" with the release,
        3 departments, 15 candidates, 5 skipped buildings and the inspection
        command as Code.
        """
        launch_uuid = "5f0c2d1e-8a3b-4c6d-9e7f-102938475600"
        BuildingImport.objects.create(
            import_source="bdtopo",
            bulk_launch_uuid=launch_uuid,
            candidate_created_count=10,
        )
        BuildingImport.objects.create(
            import_source="bdtopo",
            bulk_launch_uuid=launch_uuid,
            candidate_created_count=5,
        )
        BuildingImport.objects.create(
            import_source="bdtopo",
            bulk_launch_uuid="7a1b2c3d-4e5f-4061-8293-a4b5c6d7e8f9",
            candidate_created_count=100,
        )

        report_bdtopo_import.run(
            [3, 0, 2], bulk_launch_uuid=launch_uuid, release_date="2026-09-15"
        )

        notify_mock.assert_called_once_with(
            level=TchapLevel.SUCCESS,
            title="Import BD Topo terminé",
            details=[
                ("Millésime", "15/09/2026"),
                ("Départements traités", "3"),
                ("Candidats créés", "15"),
                ("Bâtiments sautés", "5"),
                ("À faire", "python manage.py inspect_candidates"),
            ],
        )
        self.assertIsInstance(notify_mock.call_args.kwargs["details"][4][1], Code)


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
