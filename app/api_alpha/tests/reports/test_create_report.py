import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import Building
from batid.models import Report


class CreateReportTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        self.building = Building.objects.create(
            rnb_id="TEST00000001",
            point=Point(2.3522, 48.8566, srid=4326),
            shape="POLYGON((2.3522 48.8566, 2.3523 48.8566, 2.3523 48.8567, 2.3522 48.8567, 2.3522 48.8566))",
            status="constructed",
            is_active=True,
        )

    def test_create_report_success(self):
        data = {
            "rnb_id": "TEST00000001",
            "text": "This building has an issue",
            "email": "test@example.com",
        }

        response = self.client.post(
            "/api/alpha/reports/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        response_data = response.json()
        self.assertEqual(response_data["rnb_id"], "TEST00000001")
        self.assertEqual(response_data["status"], "pending")
        self.assertEqual(response_data["author"]["display_name"], "Anonyme")

        report = Report.objects.get(id=response_data["id"])
        self.assertEqual(report.building, self.building)
        self.assertEqual(report.created_by_email, "test@example.com")
        self.assertIsNone(report.created_by_user)

    def test_create_report_authenticated_user(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        data = {
            "rnb_id": "TEST00000001",
            "text": "This building has an issue",
        }

        response = self.client.post(
            "/api/alpha/reports/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        response_data = response.json()
        self.assertEqual(response_data["rnb_id"], "TEST00000001")
        self.assertEqual(response_data["status"], "pending")
        self.assertEqual(response_data["author"]["display_name"], "Test U.")
        self.assertEqual(response_data["author"]["username"], "testuser")

        # Verify the report was created with the authenticated user
        report = Report.objects.get(id=response_data["id"])
        self.assertEqual(report.building, self.building)
        self.assertEqual(report.created_by_user, self.user)
        self.assertIsNone(report.created_by_email)

    def test_create_report_missing_rnb_id(self):
        data = {"text": "This building has an issue", "email": "test@example.com"}

        response = self.client.post(
            "/api/alpha/reports/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("rnb_id", response_data)
