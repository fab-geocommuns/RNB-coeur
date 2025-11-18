import json
from unittest import mock

from django.contrib.auth.models import Group
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import User
from batid.models import UserProfile


class BuildingPostTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        UserProfile.objects.create(user=self.user)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.group, created = Group.objects.get_or_create(
            name=RNBContributorPermission.group_name
        )

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

    def test_empty_shape(self):
        self.user.groups.add(self.group)
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1", "cle_interop_2"],
            "shape": "POLYGON EMPTY",
            "comment": "nouveau bâtiment",
        }

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json(),
            {"shape": ["La forme fournie est vide"]},
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_create_building(self):
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1", "cle_interop_2"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)
        res = r.json()

        self.assertTrue(res["rnb_id"])
        self.assertEqual(res["status"], "constructed")
        self.assertEqual(res["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        self.assertEqual(res["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        self.assertEqual(
            res["shape"],
            {
                "type": "Polygon",
                "coordinates": [
                    [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
                ],
            },
        )
        addresses = res["addresses"]
        self.assertEqual(addresses[0]["id"], "cle_interop_1")
        self.assertEqual(addresses[1]["id"], "cle_interop_2")
        self.assertEqual(len(addresses), 2)
        self.assertEqual(res["ext_ids"], [])
        self.assertTrue(res["is_active"])

        building = Building.objects.get(rnb_id=res["rnb_id"])
        event_origin = building.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_create_building_missing_status(self):
        data = {
            "addresses_cle_interop": ["cle_interop_1"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_create_building_duplicate_address(self):
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1", "cle_interop_1"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )
        res = r.json()

        building = Building.objects.get(rnb_id=res["rnb_id"])

        self.assertEqual(r.status_code, 201)
        self.assertEqual(building.addresses_id, ["cle_interop_1"])

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    @mock.patch("batid.models.requests.get")
    def test_create_building_ban_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        self.user.groups.add(self.group)
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["33063_9115_00012_bis"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 503)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_create_building_contribution_limit_exceeded(self):
        self.user.groups.add(self.group)

        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1", "cle_interop_2"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 429)

        # Verify no building was created
        buildings_count = Building.objects.count()
        self.assertEqual(buildings_count, 0)

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)
