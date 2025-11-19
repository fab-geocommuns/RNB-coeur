from unittest import mock

from django.core import signing
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from batid.models import Building
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
from batid.models import UserProfile
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
