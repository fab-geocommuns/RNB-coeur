import json
from unittest import mock

from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from api_alpha.tests.utils import coordinates_almost_equal
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import Plot
from batid.models import User
from batid.models import UserProfile


class BuildingSplitTest(APITestCase):
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

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_split_buildings(self):
        data = {
            "comment": "Ces deux bâtiments ne font qu'un !",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "notUsable",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)
        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)
        res = r.json()

        self.assertEqual(len(res), 2)
        b1 = res[0]

        self.assertEqual(b1["status"], "constructed")
        self.assertEqual(b1["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        self.assertEqual(
            b1["shape"],
            {
                "type": "Polygon",
                "coordinates": [
                    [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
                ],
            },
        )
        addresses = b1["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr1.id)
        self.assertEqual(len(addresses), 1)
        self.assertEqual(
            b1["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )

        self.assertTrue(b1["is_active"])

        b2 = res[1]
        self.assertEqual(b2["status"], "notUsable")
        self.assertEqual(b2["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        self.assertEqual(
            b1["shape"],
            {
                "type": "Polygon",
                "coordinates": [
                    [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
                ],
            },
        )
        addresses = b2["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr2.id)
        self.assertEqual(len(addresses), 1)
        self.assertEqual(
            b2["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )

        self.assertTrue(b2["is_active"])

        # little check on the parent building
        self.building_1.refresh_from_db()
        self.assertFalse(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, "split")

        event_origin = self.building_1.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, self.building_1.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_split_buildings_missing_info(self):
        self.user.groups.add(self.group)

        # base case: correct
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)

        # missing rnb_id
        data = {
            "comment": "Ce sont deux bâtiments",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "notUsable",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)

        # unknown ID-RNB
        data = {
            "comment": "Ce sont deux bâtiments",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "notUsable",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/coucoucoucou/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            r.content, b'{"detail":"No Building matches the given query."}'
        )

        # split in 1 is impossible
        data = {
            "comment": "Ce sont deux bâtiments",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                }
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.content,
            b'{"created_buildings":["Ensure this field has at least 2 elements."]}',
        )

        # missing status in child building
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.content,
            b'{"created_buildings":{"1":{"status":["Ce champ est obligatoire."]}}}',
        )

        # missing address in child building
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.content,
            b'{"created_buildings":{"1":{"addresses_cle_interop":["Ce champ est obligatoire."]}}}',
        )

        # invalid shape
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "coucou",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        unicode_content = r.content.decode("utf-8")
        self.assertEqual(
            unicode_content,
            '{"created_buildings":{"1":{"shape":["La forme fournie n\'a pas pu être analysée ou n\'est pas valide"]}}}',
        )

    @mock.patch("batid.models.requests.get")
    def test_merge_building_ban_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": ["33063_9115_00012_bis"],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 503)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @mock.patch("batid.models.requests.get")
    def test_merge_building_ban_unknown(self, get_mock):
        get_mock.return_value.status_code = 404
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "unknown",
        }

        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": ["33063_9115_00012_bis"],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    def test_split_buildings_contribution_limit_exceeded(self):
        self.user.groups.add(self.group)

        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        data = {
            "comment": "Division du bâtiment",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 429)

        # Verify the building was not split
        self.building_1.refresh_from_db()
        self.assertTrue(self.building_1.is_active)
        self.assertNotEqual(self.building_1.event_type, "split")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)
