import uuid
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.test import TestCase

from batid.models.building import Building
from batid.models.report import Report
from batid.services.reports.arcep import create_reports
from batid.services.reports.arcep import dl_and_create_arcep_reports
from batid.tests import helpers


class ReportArcepTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        if not User.objects.filter(username="RNB").exists():
            User.objects.create_user(
                username="RNB", password="password", email="rnb@example.com"
            )

    def test_create_reports_simple(self):
        # Create some points
        p1 = Point(1.0, 45.0, srid=4326)
        p2 = Point(1.1, 45.1, srid=4326)
        points = [p1, p2]

        batch_uuid = create_reports(points)

        self.assertIsInstance(batch_uuid, uuid.UUID)

        # Check reports created
        reports = Report.objects.filter(creation_batch_uuid=batch_uuid)
        self.assertEqual(reports.count(), 2)

        report1 = reports.first()
        self.assertTrue(report1.tags.filter(name="Nouveau bâtiment").exists())

    def test_create_report_nearby_building_check(self):
        # Point
        p_original = Point(2.0, 46.0, srid=4326)

        # Case 1: Real building nearby -> No report
        # Create a building very close (e.g. same location)
        # 0.00001 deg is ~1m.
        poly = Polygon.from_bbox((2.0, 46.0, 2.0001, 46.0001))
        poly.srid = 4326

        b = Building.objects.create(
            rnb_id="BDG-0000-001",
            point=p_original,
            shape=poly,
            status="constructed",
            is_active=True,
        )

        reports_uuid = create_reports([p_original])
        self.assertEqual(
            Report.objects.filter(creation_batch_uuid=reports_uuid).count(), 0
        )

        # Case 2: Building status not real -> Report created
        b.status = "demolished"
        b.save()

        reports_uuid = create_reports([p_original])
        self.assertEqual(
            Report.objects.filter(creation_batch_uuid=reports_uuid).count(), 1
        )

        # Cleanup
        Report.objects.filter(creation_batch_uuid=reports_uuid).delete()

        # Case 3: Building not active -> Report created
        b.status = "constructed"
        b.is_active = False
        b.save()

        reports_uuid = create_reports([p_original])
        self.assertEqual(
            Report.objects.filter(creation_batch_uuid=reports_uuid).count(), 1
        )

    def test_create_report_nearby_report_check(self):
        p = Point(3.0, 47.0, srid=4326)

        # Case 1: Existing report with tag nearby -> No report
        # Create existing report
        existing_report = Report.objects.create(point=p, status="pending")
        existing_report.tags.add("Nouveau bâtiment")

        reports_uuid = create_reports([p])
        # Should be 0 created because existing one is there
        self.assertEqual(
            Report.objects.filter(creation_batch_uuid=reports_uuid).count(), 0
        )

        # Case 2: Existing report checks tag
        existing_report.tags.clear()
        existing_report.tags.add("Other Tag")

        reports_uuid = create_reports([p])
        self.assertEqual(
            Report.objects.filter(creation_batch_uuid=reports_uuid).count(), 1
        )

    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.download")
    def test_import(self, sourceDownloadMock, sourceFindMock):

        sourceFindMock.return_value = helpers.fixture_path("arcep_reports_for_test.csv")
        sourceDownloadMock.return_value = None

        dl_and_create_arcep_reports()

        count = Report.objects.all().count()
        # There are 5 points in the fixture, but one is too close to another report
        self.assertEqual(count, 4)

    def test_close_irrelevant_reports(self):
        from batid.services.reports.arcep import reject_irrelevant_arcep_reports

        # 1. Setup : Une position
        p = Point(4.0, 48.0, srid=4326)

        # 2. Cas : Un rapport ARCEP existant + un bâtiment réel à proximité
        report = Report.objects.create(point=p, status="pending")
        report.tags.add("Nouveau bâtiment")

        # Bâtiment réel et actif
        poly = Polygon.from_bbox((4.0, 48.0, 4.0001, 48.0001))
        poly.srid = 4326
        Building.objects.create(
            rnb_id="BDG-CLS-001",
            point=p,
            shape=poly,
            status="constructed",
            is_active=True,
        )

        reject_irrelevant_arcep_reports()
        report.refresh_from_db()
        self.assertEqual(report.status, "rejected")

        # Verify message
        last_msg = report.messages.last()
        self.assertIn(
            "Nous fermons ce signalement car les bâtiments BDG-CLS-001 sont à moins de 10 mètres.",
            last_msg.text,
        )

    def test_close_irrelevant_reports_no_action(self):
        from batid.services.reports.arcep import reject_irrelevant_arcep_reports

        p = Point(5.0, 49.0, srid=4326)

        # Cas 1 : Bâtiment démoli (non réel) à proximité
        report_demolished = Report.objects.create(point=p, status="pending")
        report_demolished.tags.add("Nouveau bâtiment")

        poly = Polygon.from_bbox((5.0, 49.0, 5.0001, 49.0001))
        poly.srid = 4326
        Building.objects.create(
            rnb_id="BDG-CLS-002",
            point=p,
            shape=poly,
            status="demolished",  # Pas un statut "réel"
            is_active=True,
        )

        reject_irrelevant_arcep_reports()
        report_demolished.refresh_from_db()
        self.assertEqual(report_demolished.status, "pending")

        # Cas 2 : Bâtiment réel mais inactif
        p2 = Point(5.1, 49.1, srid=4326)
        report_inactive = Report.objects.create(point=p2, status="pending")
        report_inactive.tags.add("Nouveau bâtiment")

        poly2 = Polygon.from_bbox((5.1, 49.1, 5.1001, 49.1001))
        poly2.srid = 4326
        Building.objects.create(
            rnb_id="BDG-CLS-003",
            point=p2,
            shape=poly2,
            status="constructed",
            is_active=False,  # Inactif
        )

        reject_irrelevant_arcep_reports()
        report_inactive.refresh_from_db()
        self.assertEqual(report_inactive.status, "pending")

        # Cas 3 : Pas de tag "Nouveau bâtiment"
        p3 = Point(5.2, 49.2, srid=4326)
        report_tag = Report.objects.create(point=p3, status="pending")
        report_tag.tags.add("Autre tag")

        poly3 = Polygon.from_bbox((5.2, 49.2, 5.2001, 49.2001))
        poly3.srid = 4326
        Building.objects.create(
            rnb_id="BDG-CLS-004",
            point=p3,
            shape=poly3,
            status="constructed",
            is_active=True,
        )

        reject_irrelevant_arcep_reports()
        report_tag.refresh_from_db()
        self.assertEqual(report_tag.status, "pending")
