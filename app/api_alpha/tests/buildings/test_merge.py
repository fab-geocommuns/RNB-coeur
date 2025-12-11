import json
from unittest import mock

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.tests.utils import coordinates_almost_equal
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.tests.factories.users import ContributorUserFactory


class BuildingMergeTest(APITestCase):
    def setUp(self):
        self.user = ContributorUserFactory(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

        self.building_1 = Building.objects.create(
            rnb_id="AAAA00000000",
            shape="POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            is_active=True,
            addresses_id=[self.adr1.id],
            ext_ids=[
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )
        self.building_2 = Building.objects.create(
            rnb_id="BBBB00000000",
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
            is_active=True,
            addresses_id=[self.adr2.id],
            ext_ids=[
                {
                    "id": "yyy",
                    "source": "bdtopo",
                    "created_at": "2024-12-07T13:28:58.299402+00:00",
                    "source_version": "2024_01",
                }
            ],
        )

        self.building_3 = Building.objects.create(
            rnb_id="CCCC00000000",
            shape="POINT (10 0)",
            is_active=True,
            addresses_id=[],
        )

        self.building_inactive = Building.objects.create(
            rnb_id="DDDD00000000",
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
            is_active=False,
            addresses_id=[],
        )

    def test_merge_buildings_permission(self):
        self.user.groups.clear()

        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

    def test_merge_buildings(self):
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)
        res = r.json()

        self.assertTrue(res["rnb_id"])
        self.assertEqual(res["status"], "constructed")
        self.assertEqual(res["point"], {"type": "Point", "coordinates": [1.0, 0.5]})
        expectedCoordinates = [
            [
                [0.0, 1.0],
                [2.0, 1.0],
                [2.0, 0.0],
                [0.0, 0.0],
                [0.0, 1.0],
            ]
        ]
        self.assertTrue(
            coordinates_almost_equal.check(
                expectedCoordinates, res["shape"]["coordinates"]
            )
        )
        self.assertEqual(res["shape"]["type"], "Polygon")
        addresses = res["addresses"]
        addresses_ids = [address["id"] for address in addresses]
        addresses_ids.sort()

        expected_addresses = [self.adr1.id, self.adr2.id]
        expected_addresses.sort()

        self.assertListEqual(addresses_ids, expected_addresses)

        self.assertEqual(len(addresses), 2)
        self.assertEqual(
            res["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                },
                {
                    "id": "yyy",
                    "source": "bdtopo",
                    "created_at": "2024-12-07T13:28:58.299402+00:00",
                    "source_version": "2024_01",
                },
            ],
        )

        self.assertTrue(res["is_active"])

        building = Building.objects.get(rnb_id=res["rnb_id"])
        event_origin = building.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_merge_buildings_explicit_addresses(self):
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            # we put a duplicate on purpose
            "addresses_cle_interop": [self.adr1.id, self.adr1.id],
            "comment": "Ces deux bâtiments ne font qu'un, mais une seule adresse est la bonne",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)
        res = r.json()

        self.assertTrue(res["rnb_id"])
        self.assertEqual(res["status"], "constructed")
        self.assertEqual(res["point"], {"type": "Point", "coordinates": [1.0, 0.5]})

        addresses = res["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr1.id)
        self.assertEqual(len(addresses), 1)

        self.assertEqual(
            res["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                },
                {
                    "id": "yyy",
                    "source": "bdtopo",
                    "created_at": "2024-12-07T13:28:58.299402+00:00",
                    "source_version": "2024_01",
                },
            ],
        )
        self.assertTrue(res["is_active"])

        building = Building.objects.get(rnb_id=res["rnb_id"])
        event_origin = building.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_merge_buildings_bad_requests(self):

        # not enough rnb_ids to merge
        data = {
            "rnb_ids": [],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # rnb_ids should be a list
        data = {
            "rnb_ids": "coucou",
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # missing status
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # missing addresses
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "comment": "Ces deux bâtiments ne font qu'un, mais une seule adresse est la bonne",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # shapes must be contiguous
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_3.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "Pour fusionner des bâtiments, leurs géométries doivent être des polygones contigus. Veuillez d'abord mettre à jour les géométries des bâtiments",
            r.json()["detail"],
        )

        # one building is not enough
        data = {
            "rnb_ids": [self.building_1.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json(), {"rnb_ids": ["Ensure this field has at least 2 elements."]}
        )

        # cannot merge inactive buildings
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_inactive.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "Cette opération est impossible sur un ID-RNB inactif",
            r.json()["detail"],
        )

        # comment is not mandatory
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [self.adr1.id],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)

    @mock.patch("batid.models.requests.get")
    def test_merge_building_ban_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": ["33063_9115_00012_bis"],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 503)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    def test_merge_buildings_contribution_limit_exceeded(self):

        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Fusion de bâtiments",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

        # Verify the buildings were not merged
        self.building_1.refresh_from_db()
        self.building_2.refresh_from_db()
        self.assertTrue(self.building_1.is_active)
        self.assertTrue(self.building_2.is_active)
        self.assertNotEqual(self.building_1.event_type, "merge")
        self.assertNotEqual(self.building_2.event_type, "merge")

    def test_merge_buildings_contribution_limit_exceeded_but_sandbox(self):

        with self.settings(ENVIRONMENT="sandbox"):

            # Set user to have reached their contribution limit
            self.user.profile.total_contributions = 500
            self.user.profile.max_allowed_contributions = 500
            self.user.profile.save()

            data = {
                "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
                "status": "constructed",
                "merge_existing_addresses": True,
                "comment": "Fusion de bâtiments",
            }

            r = self.client.post(
                f"/api/alpha/buildings/merge/",
                data=json.dumps(data),
                content_type="application/json",
            )

            self.assertEqual(r.status_code, 201)

            # Verify the buildings were not merged
            self.building_1.refresh_from_db()
            self.building_2.refresh_from_db()
            self.assertFalse(self.building_1.is_active)
            self.assertFalse(self.building_2.is_active)
            self.assertEqual(self.building_1.event_type, "merge")
            self.assertEqual(self.building_2.event_type, "merge")

            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.total_contributions, 501)
