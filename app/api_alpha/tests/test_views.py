from unittest import mock

from django.core import signing
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from batid.models import Building
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
from batid.services.kpi import compute_today_kpis


class StatsTest(APITestCase):
    @mock.patch("api_alpha.views.requests.get")
    def test_stats(self, get_mock):

        # create buildings for building count
        Building.objects.create(rnb_id="1", is_active=True)
        Building.objects.create(rnb_id="2", is_active=True)
        Building.objects.create(rnb_id="3", is_active=False)
        # trigger the stats computation for building count
        compute_today_kpis()

        # create one "report" (signalement) contribution
        Contribution.objects.create(report=True)
        # and one edition
        Contribution.objects.create(report=False)

        DiffusionDatabase.objects.create()

        # log 2 API request, one is older than 2024
        APIRequestLog.objects.create(requested_at="2023-01-01T00:00:00Z")
        APIRequestLog.objects.create(requested_at="2024-01-02T00:00:00Z")

        # mock the data.gouv API
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {"total": 12}

        r = self.client.get("/api/alpha/stats")
        self.assertEqual(r.status_code, 200)
        results = r.json()

        self.assertEqual(results["building_counts"], 2)
        self.assertLess(results["building_counts"], 4)
        self.assertEqual(results["api_calls_since_2024_count"], 1)
        self.assertEqual(results["reports_count"], 1)
        self.assertEqual(results["editions_count"], 1)
        self.assertEqual(results["data_gouv_publication_count"], 11)
        self.assertEqual(results["diffusion_databases_count"], 1)

        # assert the mock was called
        get_mock.assert_called_with("https://www.data.gouv.fr/api/1/datasets/?tag=rnb")


class ContributionTest(APITestCase):
    def test_contribution(self):

        Building.objects.create(rnb_id="1")
        Contribution.objects.create(rnb_id="1", text="", email="riri@email.fr")

        data = {"email": "loulou@email.fr", "text": "test", "rnb_id": "1"}
        r = self.client.post("/api/alpha/contributions/", data)

        self.assertEqual(r.status_code, 201)
        self.assertEqual(Contribution.objects.count(), 2)
        # loulou is expected at the second place, ex aequo with fifi
        self.assertEqual(
            r.json(),
            {
                "rnb_id": "1",
                "text": "test",
                "email": "loulou@email.fr",
            },
        )

    # @freeze_time("2024-08-05")
    # def test_ranking(self):
    #     from batid.models import Department_subdivided
    #
    #     create_grenoble()
    #     create_paris()
    #
    #     Department_subdivided.objects.create(
    #         code="75",
    #         name="Paris",
    #         shape=GEOSGeometry(
    #             json.dumps(
    #                 {
    #                     "coordinates": [
    #                         [
    #                             [2.353306071148694, 48.90085197679912],
    #                             [2.298936023110457, 48.89580357010155],
    #                             [2.273133288448662, 48.87419062799353],
    #                             [2.2602319211170823, 48.84630219945575],
    #                             [2.313373267504062, 48.82102752865572],
    #                             [2.372965297558153, 48.81678013291423],
    #                             [2.4175057323916462, 48.84407854008418],
    #                             [2.411362224139367, 48.878837188722514],
    #                             [2.3907814714921187, 48.89964040569237],
    #                             [2.353306071148694, 48.90085197679912],
    #                         ]
    #                     ],
    #                     "type": "Polygon",
    #                 }
    #             ),
    #             srid=4326,
    #         ),
    #     )
    #
    #     Department_subdivided.objects.create(
    #         code="01",
    #         name="Ain",
    #         shape=GEOSGeometry(
    #             "POLYGON ((-1.1445170773446591 50.14048784607837, -1.1445170773446591 48.46067765220832, 2.180844882808316 48.46067765220832, 2.180844882808316 50.14048784607837, -1.1445170773446591 50.14048784607837))"
    #         ),
    #     )
    #
    #     Department_subdivided.objects.create(
    #         code="02",
    #         name="Aisne",
    #         shape=GEOSGeometry(
    #             "POLYGON ((4.023367285356358 49.55818275540048, 4.023367285356358 48.001809772072534, 7.459707468976717 48.001809772072534, 7.459707468976717 49.55818275540048, 4.023367285356358 49.55818275540048))"
    #         ),
    #     )
    #
    #     # Buildings in Paris
    #     Building.objects.create(
    #         rnb_id="p_1",
    #         point=GEOSGeometry("POINT (2.3151031002108637 48.853855939132494)"),
    #     )
    #     Building.objects.create(
    #         rnb_id="p_2",
    #         point=GEOSGeometry("POINT (2.366944834508937 48.87440863357778)"),
    #     )
    #
    #     # Contributions in Paris
    #     Contribution.objects.create(rnb_id="p_1", text="", email="lucie@dummy.fr")
    #     Contribution.objects.create(rnb_id="p_2", text="", email="lucie@dummy.fr")
    #
    #     # Buildings in Ain
    #     Building.objects.create(rnb_id="1_1", point=GEOSGeometry("POINT (0 49)"))
    #     Building.objects.create(rnb_id="1_2", point=GEOSGeometry("POINT (0 49)"))
    #     # Buildings in Aisne
    #     Building.objects.create(rnb_id="2_1", point=GEOSGeometry("POINT (5 49)"))
    #     Building.objects.create(rnb_id="2_2", point=GEOSGeometry("POINT (5 49)"))
    #
    #     # Contributions in Ain
    #     Contribution.objects.create(rnb_id="1_1", text="", email="riri@email.fr")
    #     Contribution.objects.create(rnb_id="1_2", text="", email="fifi@email.fr")
    #     Contribution.objects.create(rnb_id="1_2", text="", email="loulou@email.fr")
    #
    #     # Contributions in Aisne
    #     Contribution.objects.create(rnb_id="2_1", text="", email="riri@email.fr")
    #     Contribution.objects.create(rnb_id="2_2", text="", email="fifi@email.fr")
    #
    #     # refused contribution
    #     Contribution.objects.create(
    #         rnb_id="2_1", text="", email="riri@email.fr", status="refused"
    #     )
    #
    #     r = self.client.get("/api/alpha/contributions/ranking/")
    #     response = r.json()
    #
    #     self.assertEqual(r.status_code, 200)
    #     self.assertTrue("departement" in response)
    #     self.assertTrue("city" in response)
    #     self.assertTrue("individual" in response)
    #
    #     # individual ranking : [[count1, rank1], [count2, rank2], ...]
    #     # departement ranking : [[dpt_code1, dpt_name1, dpt_count1], [dpt_code2, dpt_name2, dpt_count2], ...]
    #     self.assertEqual(
    #         response,
    #         {
    #             "individual": [[2, 1], [2, 1], [2, 1], [1, 4]],
    #             "departement": [
    #                 ["01", "Ain", 3],
    #                 ["02", "Aisne", 2],
    #                 ["75", "Paris", 2],
    #             ],
    #             "city": [["75056", "Paris", 2]],
    #             "global": 7,
    #         },
    #     )

    def test_contribution_permissions_list(self):
        # you cannot list contributions
        r = self.client.get("/api/alpha/contributions/")
        self.assertEqual(r.status_code, 405)

    def test_contribution_permissions_read(self):
        Building.objects.create(rnb_id="xxx")
        c = Contribution.objects.create(rnb_id="xxx", text="", email="riri@email.fr")

        r = self.client.get(f"/api/alpha/contributions/{c.id}/")
        # you cannot access a contribution after it has been created
        # I was expecting a 405, but DRF is returning a 404
        self.assertEqual(r.status_code, 404)


class TestDiffusionDatabases(APITestCase):
    def test_diffusion_databases(self):
        # create a diffusion database
        DiffusionDatabase.objects.create(
            name="Fichiers fonciers",
            documentation_url="https://datafoncier.cerema.fr/actualites/nouveau-millesime-fichiers-fonciers-2024-disponible?ref=referentiel-national-du-batiment.ghost.io",
            publisher="le Cerema",
            licence="Réservée aux ayant droits",
        )
        url = "/api/alpha/diffusion_databases"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Fichiers fonciers", response.content.decode())


class TestOrganizationNames(APITestCase):
    def test_organization_names(self):
        Organization.objects.create(name="CC de la Varne")
        Organization.objects.create(name="Mairie de Saint-Brégorin")
        url = "/api/alpha/organization_names"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("CC de la Varne", response.content.decode())
        self.assertIn("Mairie de Saint-Brégorin", response.content.decode())


class TestDebugViews(APITestCase):
    def test_error_endpoint_with_valid_token(self):
        token = signing.dumps("error-test", salt="error-test")

        with self.assertRaises(Exception) as context:
            self.client.get(f"/__test__/error/?token={token}")

        self.assertEqual(str(context.exception), "This is a test error")
