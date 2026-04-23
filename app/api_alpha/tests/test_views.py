from batid.models import DiffusionDatabase, Organization
from django.core import signing
from rest_framework.test import APITestCase


class TestDiffusionDatabases(APITestCase):
    def test_diffusion_databases(self):
        # create a diffusion database
        DiffusionDatabase.objects.create(
            name="Fichiers fonciers",
            documentation_url="https://datafoncier.cerema.fr/actualites/nouveau-millesime-fichiers-fonciers-2024-disponible?ref=referentiel-national-du-batiment.ghost.io",
            publisher="le Cerema",
            licence="Réservée aux ayant droits",
        )
        DiffusionDatabase.objects.create(
            name="Petite ville",
            documentation_url="https://petiteville.fr",
            publisher="La petite ville",
            licence="Réservée aux ayant droits",
            is_displayed=False,
        )
        url = "/api/alpha/diffusion_databases"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # is_displayed is True by default
        self.assertIn("Fichiers fonciers", response.content.decode())
        self.assertNotIn("Petite ville", response.content.decode())


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
