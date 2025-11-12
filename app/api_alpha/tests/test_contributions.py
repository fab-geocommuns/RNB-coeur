from rest_framework.test import APITestCase

from batid.models import Building
from batid.models import Report
from batid.models import ReportMessage
from batid.models import Contribution
from django.contrib.gis.geos import Point


class TestContribution(APITestCase):
    def test_contribution_permissions_list(self):
        # you cannot list contributions
        r = self.client.get("/api/alpha/contributions/")
        self.assertEqual(r.status_code, 405)

    def test_contribution_permissions_read(self):
        building = Building.objects.create(
            rnb_id="xxx", point=Point(2.3522, 48.8566, srid=4326)
        )
        report = Report.objects.create(
            point=Point(2.3522, 48.8566, srid=4326),
            building=building,
            created_by_email="riri@email.test",
        )
        report.messages.create(text="", created_by_email="riri@email.test")

        r = self.client.get(f"/api/alpha/contributions/{report.id}/")
        # you cannot access a contribution after it has been created
        # I was expecting a 405, but DRF is returning a 404
        self.assertEqual(r.status_code, 404)

    def test_contribution(self):

        building = Building.objects.create(
            rnb_id="1", point=Point(2.3522, 48.8566, srid=4326)
        )
        report = Report.objects.create(
            point=Point(2.3522, 48.8566, srid=4326),
            building=building,
            created_by_email="riri@email.test",
        )
        report.messages.create(text="", created_by_email="riri@email.test")

        data = {"email": "loulou@email.fr", "text": "test", "rnb_id": "1"}
        r = self.client.post("/api/alpha/contributions/", data)

        self.assertEqual(r.status_code, 201)
        self.assertEqual(Report.objects.count(), 2)
        response_data = r.json()
        self.assertEqual(response_data["rnb_id"], "1")
        self.assertEqual(response_data["messages"][0]["text"], "test")
        self.assertEqual(response_data["author"]["display_name"], "Anonyme")

    def test_create_contribution(self):
        """"""

        # Create a building
        Building.objects.create(rnb_id="111", point=Point(2.3522, 48.8566, srid=4326))

        # Post a contribution about it
        r = self.client.post(
            "/api/alpha/contributions/", data={"rnb_id": "111", "text": "I exist"}
        )
        self.assertEqual(r.status_code, 201)

        report = Report.objects.first()
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(report.messages.first().text, "I exist")
        self.assertEqual(report.building.rnb_id, "111")
        self.assertEqual(report.status, "pending")

    def test_create_inactive_bdg(self):
        """
        It should not be possible to post a new contribution about an inactive building
        :return:
        """

        # The inactive building
        Building.objects.create(rnb_id="AAA", is_active=False)

        # Post a contribution about it
        r = self.client.post(
            "/api/alpha/contributions/",
            data={"rnb_id": "AAA", "text": "I shoud not exist"},
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json(), {"rnb_id": ["L'ID-RNB \"AAA\" n'est pas actif."]})
