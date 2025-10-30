from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.db.utils import IntegrityError
from django.test import TestCase

from batid.models import Building
from batid.models import Report
from batid.models import ReportMessage


class TestReportMessage(TestCase):
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

        self.report = Report.objects.create(
            point=self.point,
            building=self.building,
            created_by_user=self.user,
            status="pending",
        )

    def test_report_message_creation_with_user_succeeds(self):
        message = self.report.messages.create(
            created_by_user=self.user,
            text="This is a test message from a user",
        )

        self.assertEqual(message.report, self.report)
        self.assertEqual(message.created_by_user, self.user)
        self.assertIsNone(message.created_by_email)
        self.assertEqual(message.text, "This is a test message from a user")
        self.assertIsNotNone(message.timestamp)

    def test_report_message_creation_with_email_succeeds(self):
        message = self.report.messages.create(
            created_by_email="commenter@example.com",
            text="This is a test message from an email user",
        )

        self.assertEqual(message.report, self.report)
        self.assertIsNone(message.created_by_user)
        self.assertEqual(message.created_by_email, "commenter@example.com")
        self.assertEqual(message.text, "This is a test message from an email user")
        self.assertIsNotNone(message.timestamp)

    def test_report_message_creation_with_both_user_and_email_fails(self):
        with self.assertRaises(IntegrityError) as context:
            self.report.messages.create(
                created_by_user=self.user,
                created_by_email="commenter@example.com",
                text="This should fail",
            )

        # Check that the error is related to our constraint
        self.assertIn("report_message_creator_exclusive", str(context.exception))

    def test_report_message_creation_without_creator_fails(self):
        with self.assertRaises(IntegrityError) as context:
            self.report.messages.create(
                text="This should fail - no creator",
            )

        # Check that the error is related to our constraint
        self.assertIn("report_message_creator_exclusive", str(context.exception))

    def test_report_message_requires_text(self):
        # Text field is required, so this should fail
        with self.assertRaises(IntegrityError):
            self.report.messages.create(
                created_by_user=self.user,
                # No text provided
            )

    def test_report_message_requires_report(self):
        # Report field is required, so this should fail
        with self.assertRaises(IntegrityError):
            ReportMessage.objects.create(
                created_by_user=self.user,
                text="This should fail - no report",
            )

    def test_report_message_ordering(self):
        # Create multiple messages to test ordering
        message1 = self.report.messages.create(
            created_by_user=self.user,
            text="First message",
        )

        message2 = self.report.messages.create(
            created_by_email="another@example.com",
            text="Second message",
        )

        messages = list(self.report.messages.all())
        self.assertEqual(messages[0], message1)
        self.assertEqual(messages[1], message2)

    def test_report_message_cascade_delete(self):
        message = self.report.messages.create(
            created_by_user=self.user,
            text="This message should be deleted with the report",
        )

        message_id = message.id
        self.assertTrue(ReportMessage.objects.filter(id=message_id).exists())

        # Delete the report - message should be cascade deleted
        self.report.delete()
        self.assertFalse(ReportMessage.objects.filter(id=message_id).exists())
