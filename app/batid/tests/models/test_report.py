from batid.models import Building, Report
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase


class TestReport(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )
        self.point = Point(2.3522, 48.8566, srid=4326)

        self.building = Building.objects.create(
            rnb_id="TEST123",
            point=self.point,
            status="constructed",
        )

    def test_report_creation_without_point_fails(self):
        with self.assertRaises(IntegrityError) as context:
            with transaction.atomic():
                Report.objects.create(
                    building=self.building,
                    created_by_user=self.user,
                    status="pending",
                )

    def test_report_creation_with_user_succeeds(self):
        report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_user=self.user,
            status="pending",
        )

        self.assertEqual(report.created_by_user, self.user)
        self.assertIsNone(report.created_by_email)
        self.assertEqual(report.status, "pending")

    def test_report_creation_with_email_succeeds(self):
        report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_email="reporter@example.com",
            status="pending",
        )

        self.assertIsNone(report.created_by_user)
        self.assertEqual(report.created_by_email, "reporter@example.com")
        self.assertEqual(report.status, "pending")

    def test_report_creation_with_both_user_and_email_fails(self):
        with self.assertRaises(IntegrityError) as context:
            Report.objects.create(
                point=self.point,
                building=self.building,
                created_by_user=self.user,
                created_by_email="reporter@example.com",
                status="pending",
            )

        self.assertIn("report_creator_not_both", str(context.exception))

    def test_report_creation_without_creator_succeeds(self):
        report = Report.objects.create(
            point=self.point,
            building=self.building,
            status="pending",
        )

        self.assertIsNone(report.created_by_user)
        self.assertIsNone(report.created_by_email)
        self.assertEqual(report.status, "pending")

    def test_report_creation_with_null_building_succeeds(self):
        report = Report.objects.create(
            point=self.point,
            building=None,
            created_by_user=self.user,
            status="pending",
        )

        self.assertIsNone(report.building)
        self.assertEqual(report.created_by_user, self.user)

    def test_report_default_status(self):
        report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_user=self.user,
        )

        self.assertEqual(report.status, "pending")

    def test_report_closed_by_user(self):
        closer_user = User.objects.create_user(
            username="closer", email="closer@example.com"
        )

        report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_user=self.user,
            closed_by_user=closer_user,
            status="fixed",
        )

        self.assertEqual(report.closed_by_user, closer_user)

    def test_report_creation_with_tags_succeeds(self):
        report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_user=self.user,
            status="pending",
        )

        report.tags.add("tag1", "tag2")

        self.assertEqual(report.tags.count(), 2)
        self.assertIn("tag1", report.tags.names())
        self.assertIn("tag2", report.tags.names())

    def test_add_message_returns_created_message_and_feve_flag(self):
        """
        Input: add_message_and_update_status on an open report (no feve attached).
        Expected: returns (ReportMessage, False) where the message is the one
                  persisted on the report with the given text and status applied.
        """
        report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_user=self.user,
            status="pending",
        )

        message, feve_found = report.add_message_and_update_status(
            text="Fixed it",
            created_by_user=self.user,
            created_by_email=None,
            status="fixed",
        )

        self.assertFalse(feve_found)
        self.assertEqual(message, report.messages.last())
        self.assertEqual(message.text, "Fixed it")
        report.refresh_from_db()
        self.assertEqual(report.status, "fixed")
