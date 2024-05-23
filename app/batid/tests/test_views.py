from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from batid.models import Address
from batid.models import Building
from batid.models import Contribution


def create_superuser_and_login(self):
    self.superuser = User.objects.create_superuser(
        username="superuser", email="superuser@test.com", password="password"
    )
    self.client.login(username="superuser", password="password")


class TestContributionsViews(TestCase):
    def test_delete_building_403(self):
        # create a building
        rnb_id = "1234"
        Building.objects.create(rnb_id=rnb_id)

        # create a contribution about this building
        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment n'existe pas"
        )

        url = reverse("delete_building")
        data = {"rnb_id": rnb_id, "contribution_id": contribution.id}
        response = self.client.post(url, data)
        # we expect a 403: for the moment only superuser can contribute
        self.assertEqual(response.status_code, 403)

    def test_delete_building(self):
        create_superuser_and_login(self)

        # create a building
        rnb_id = "1234"
        building = Building.objects.create(rnb_id=rnb_id)

        # create a contribution about this building
        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment n'existe pas"
        )

        url = reverse("delete_building")
        data = {
            "rnb_id": rnb_id,
            "contribution_id": contribution.id,
            "review_comment": "OK",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        # Check the html content of the response
        self.assertIn(f"Revue de contribution enregistrée.", response.content.decode())

        # Check that the building has been deleted
        building.refresh_from_db()
        self.assertEqual(building.event_type, "delete")
        self.assertIsNotNone(building.event_id)
        self.assertFalse(building.is_active)
        self.assertEqual(building.event_user, self.superuser)

        # Check that the contribution has been fixed
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "fixed")
        self.assertIsNotNone(contribution.status_changed_at)
        self.assertEqual(contribution.review_comment, "OK")
        self.assertEqual(contribution.review_user, self.superuser)

    def test_delete_building_400_inactive_building(self):
        create_superuser_and_login(self)

        # create a inactive building
        rnb_id = "1234"
        Building.objects.create(rnb_id=rnb_id, is_active=False)

        # create a contribution about this building
        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment n'existe pas"
        )

        url = reverse("delete_building")
        data = {
            "rnb_id": rnb_id,
            "contribution_id": contribution.id,
            "review_comment": "OK",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.content.decode(), "Cannot delete an inactive building."
        )

    def test_delete_building_400_fixed_contrib(self):
        create_superuser_and_login(self)

        # create a inactive building
        rnb_id = "1234"
        Building.objects.create(rnb_id=rnb_id)

        # create a contribution about this building
        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment n'existe pas", status="rejected"
        )

        url = reverse("delete_building")
        data = {
            "rnb_id": rnb_id,
            "contribution_id": contribution.id,
            "review_comment": "OK",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), "Contribution is not pending.")

    def test_contribution_404(self):
        create_superuser_and_login(self)

        url = reverse("delete_building")

        # we post a request with non existing contribution and building ids
        data = {
            "rnb_id": "rnb_id",
            "contribution_id": 1,
            "review_comment": "OK",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)

        self.assertIn(
            "The requested resource was not found on this server",
            response.content.decode(),
        )

    def test_refuse_contribution_403(self):
        rnb_id = "1234"
        Building.objects.create(rnb_id=rnb_id)

        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment n'existe pas"
        )

        url = reverse("refuse_contribution")
        data = {"review_comment": "si, il existe", "contribution_id": contribution.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_refuse_contribution(self):
        create_superuser_and_login(self)

        rnb_id = "1234"
        building = Building.objects.create(rnb_id=rnb_id, event_type="create")

        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment n'existe pas"
        )

        url = reverse("refuse_contribution")
        data = {
            "contribution_id": contribution.id,
            "review_comment": "faux ! il existe.",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        # Check the html content of the response
        self.assertIn("Revue de contribution enregistrée.", response.content.decode())

        # Check that the building has not been modified.
        building.refresh_from_db()
        self.assertEqual(building.event_type, "create")
        self.assertIsNone(building.event_id)
        self.assertTrue(building.is_active)
        self.assertIsNone(building.event_user)

        # Check that the contribution has been refused
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "refused")
        self.assertIsNotNone(contribution.status_changed_at)
        self.assertEqual(contribution.review_comment, "faux ! il existe.")
        self.assertEqual(contribution.review_user, self.superuser)

    def test_update_addresses_contribution_403(self):
        rnb_id = "1234"
        Building.objects.create(rnb_id=rnb_id)

        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce batiment est au 12 de la rue"
        )

        url = reverse("update_building_addresses")
        data = {
            "review_comment": "mise à jour de l'adresse",
            "contribution_id": contribution.id,
            "addresses_id": "1,2,3",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_update_addresses_contribution(self):
        create_superuser_and_login(self)

        rnb_id = "1234"
        building = Building.objects.create(rnb_id=rnb_id, event_type="create")

        address_1 = Address.objects.create(id="1")
        address_2 = Address.objects.create(id="2")

        contribution = Contribution.objects.create(
            rnb_id=rnb_id, text="Ce bâtiment est au 12 de la rue"
        )

        url = reverse("update_building_addresses")
        data = {
            "contribution_id": contribution.id,
            "rnb_id": rnb_id,
            "review_comment": "mise à jour de l'adresse.",
            "addresses_id": f"{address_1.id},{address_2.id}",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        # Check the html content of the response
        self.assertIn("Revue de contribution enregistrée.", response.content.decode())

        # Check that the building has not been modified.
        building.refresh_from_db()
        self.assertEqual(building.event_type, "update")
        self.assertIsNotNone(building.event_id)
        self.assertTrue(building.is_active)
        self.assertIsNotNone(building.event_user)
        # addresses are updated
        self.assertEqual(building.addresses_id, [address_1.id, address_2.id])

        # Check that the contribution has been updated
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "fixed")
        self.assertIsNotNone(contribution.status_changed_at)
        self.assertEqual(contribution.review_comment, "mise à jour de l'adresse.")
        self.assertEqual(contribution.review_user, self.superuser)
