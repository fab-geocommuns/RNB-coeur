import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import Building
from batid.models import Report


class ReplyToReportTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.token = Token.objects.create(user=self.user)

        self.building = Building.objects.create(
            rnb_id="TEST00000001",
            point=Point(2.3522, 48.8566, srid=4326),
            shape="POLYGON((2.3522 48.8566, 2.3523 48.8566, 2.3523 48.8567, 2.3522 48.8567, 2.3522 48.8566))",
            status="constructed",
            is_active=True,
        )

        self.report = Report.create(
            point=self.building.point,
            building=self.building,
            text="This building has an issue",
            email="reporter@example.com",
            user=None,
            tags=["Signalement utilisateur"],
        )

    def test_reply_logged_in_user_without_changing_status(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        data = {
            "message": "Indeed",
            "action": "comment",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        self.assertEqual(response_data["id"], self.report.id)
        self.assertEqual(response_data["status"], "pending")
        self.assertEqual(len(response_data["messages"]), 2)
        self.assertEqual(
            response_data["messages"][1]["text"],
            "Indeed",
        )
        self.assertEqual(response_data["messages"][1]["author"]["username"], "testuser")

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "pending")
        self.assertEqual(self.report.closed_by_user, None)
        self.assertEqual(self.report.closed_by_event_id, None)
        self.assertEqual(self.report.messages.count(), 2)
        self.assertEqual(self.report.messages.last().text, "Indeed")
        self.assertEqual(self.report.messages.last().created_by_user, self.user)
        self.assertIsNone(self.report.messages.last().created_by_email)

    def test_reply_logged_out_user_without_changing_status(self):
        data = {
            "message": "Indeed",
            "email": "anonymous@example.com",
            "action": "comment",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        self.assertEqual(response_data["id"], self.report.id)
        self.assertEqual(response_data["status"], "pending")
        self.assertEqual(len(response_data["messages"]), 2)
        self.assertEqual(response_data["messages"][1]["text"], "Indeed")
        self.assertEqual(
            response_data["messages"][1]["author"]["display_name"], "Anonyme"
        )

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "pending")
        self.assertEqual(self.report.closed_by_user, None)
        self.assertEqual(self.report.messages.count(), 2)
        self.assertEqual(self.report.messages.last().text, "Indeed")
        self.assertIsNone(self.report.messages.last().created_by_user)
        self.assertEqual(
            self.report.messages.last().created_by_email, "anonymous@example.com"
        )

    def test_reply_logged_in_user_changing_status(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        data = {
            "message": "This has been fixed",
            "action": "fix",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        self.assertEqual(response_data["id"], self.report.id)
        self.assertEqual(response_data["status"], "fixed")
        self.assertEqual(len(response_data["messages"]), 2)
        self.assertEqual(response_data["messages"][1]["text"], "This has been fixed")
        self.assertEqual(response_data["messages"][1]["author"]["username"], "testuser")

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "fixed")
        self.assertEqual(self.report.closed_by_user, self.user)
        self.assertEqual(self.report.messages.count(), 2)
        self.assertEqual(self.report.messages.last().text, "This has been fixed")
        self.assertEqual(self.report.messages.last().created_by_user, self.user)
        self.assertIsNone(self.report.messages.last().created_by_email)

    def test_reply_logged_out_user_changing_status(self):
        # 400 as a logged-out user cannot change status
        data = {
            "message": "I don't think so",
            "action": "reject",
            "email": "anonymous@example.com",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("action", response_data)
        self.assertEqual(
            response_data["action"][0],
            "Vous devez être connecté pour changer le statut du signalement.",
        )

        # Verify the report status was not changed
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "pending")
        self.assertIsNone(self.report.closed_by_user)
        # No message should have been added
        self.assertEqual(self.report.messages.count(), 1)

    def test_reply_with_invalid_action(self):
        # 400 as invalid action
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        data = {
            "message": "This is a reply",
            "action": "invalid_action",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("action", response_data)

        # Verify no changes were made
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "pending")
        self.assertEqual(self.report.messages.count(), 1)

    def test_reply_with_no_action(self):
        # 400 as action is required
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        data = {
            "message": "This is a reply",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("action", response_data)

    def test_reply_with_no_message(self):
        # 400 as message is required
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        data = {
            "action": "fix",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("message", response_data)

        # Verify no changes were made
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "pending")
        self.assertEqual(self.report.messages.count(), 1)

    def test_reply_to_closed_report(self):
        # 400 as closed reports cannot receive new messages
        # First close the report
        self.report.status = "fixed"
        self.report.closed_by_user = self.user
        self.report.save()

        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        data = {
            "message": "This should fail",
            "action": "comment",
        }

        response = self.client.post(
            f"/api/alpha/reports/{self.report.id}/reply/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # The add_message method raises ValueError, which is caught and returns 400
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("non_field_errors", response_data)
        self.assertEqual(
            response_data["non_field_errors"][0],
            "Le signalement est déjà clos.",
        )

        # Verify no new message was added
        self.report.refresh_from_db()
        self.assertEqual(self.report.messages.count(), 1)
