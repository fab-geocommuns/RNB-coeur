from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rest_framework.test import APITestCase

from batid.models import Building
from batid.models import Report
from batid.models import ReportMessage


class GetReportTest(APITestCase):
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

        self.report = Report.objects.create(
            point=Point(2.3522, 48.8566, srid=4326),
            building=self.building,
            status="pending",
            created_by_user=self.user,
        )

        self.report.tags.add("tag1", "tag2")

        self.first_message = ReportMessage.objects.create(
            report=self.report,
            created_by_user=self.user,
            text="Ce bâtiment n'existe pas",
        )

        self.second_message = ReportMessage.objects.create(
            report=self.report,
            created_by_email="another@example.com",
            text="J'habite à côté je confirme",
        )

    def test_get_report(self):
        response = self.client.get(f"/api/alpha/reports/{self.report.id}/")

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["id"], self.report.id)
        self.assertEqual(data["rnb_id"], self.building.rnb_id)

        self.assertEqual(data["point"]["type"], "Point")
        self.assertEqual(data["point"]["coordinates"], [2.3522, 48.8566])

        author = data["author"]
        self.assertEqual(author["display_name"], "Test U.")
        self.assertCountEqual(data["tags"], ["tag1", "tag2"])

        self.assertEqual(len(data["messages"]), 2)

        message = data["messages"][0]
        self.assertEqual(message["text"], "Ce bâtiment n'existe pas")
        self.assertEqual(message["author"]["username"], "testuser")

        message = data["messages"][1]
        self.assertEqual(message["text"], "J'habite à côté je confirme")
        self.assertEqual(message["author"]["username"], None)
        self.assertEqual(message["author"]["display_name"], "Anonyme")

    def test_get_report_without_building(self):
        report_without_building = Report.objects.create(
            point=Point(2.3522, 48.8566, srid=4326),
            building=None,
            status="pending",
            created_by_user=self.user,
        )

        response = self.client.get(f"/api/alpha/reports/{report_without_building.id}/")

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["id"], report_without_building.id)
        self.assertIsNone(data["rnb_id"])

    def test_get_nonexistent_report(self):
        response = self.client.get("/api/alpha/reports/99999/")

        self.assertEqual(response.status_code, 404)
