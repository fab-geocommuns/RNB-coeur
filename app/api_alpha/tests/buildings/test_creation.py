import json
import uuid
from unittest import mock

from batid.models import Address, Building, Contribution, SummerChallenge
from batid.tests.factories.users import ContributorUserFactory
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class BuildingPostTest(APITestCase):
    def setUp(self):
        self.user = ContributorUserFactory(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

    def test_empty_shape(self):
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
    def test_create_building_permission(self):
        self.user.groups.clear()

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

        self.assertEqual(contribution.user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_create_building_missing_status(self):
        data = {
            "addresses_cle_interop": ["cle_interop_1"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

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

        self.assertEqual(r.status_code, 403)

        # Verify no building was created
        buildings_count = Building.objects.count()
        self.assertEqual(buildings_count, 0)

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_create_building_contribution_limit_exceeded_but_staff(self):
        self.user.is_staff = True
        self.user.save()

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

        self.assertEqual(r.status_code, 201)

        # Verify building was created
        buildings_count = Building.objects.count()
        self.assertEqual(buildings_count, 1)

        # Verify user contribution count did increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 501)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_create_building_contribution_limit_exceeded_but_sandbox(self):

        with self.settings(ENVIRONMENT="sandbox"):
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

            self.assertEqual(r.status_code, 201)

            # Verify no building was created
            buildings_count = Building.objects.count()
            self.assertEqual(buildings_count, 1)

            # Verify user contribution count did not increase
            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.total_contributions, 501)


@override_settings(MAX_BUILDING_AREA=float("inf"))
class BuildingPostIsValidTest(APITestCase):
    """Tests for the `is_valid` parameter on POST /api/alpha/buildings/."""

    def setUp(self):
        self.user = ContributorUserFactory(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.data = {
            "status": "constructed",
            "addresses_cle_interop": [],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

    def _post(self, data):
        return self.client.post(
            "/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_create_with_is_valid_true(self):
        """
        Input: POST creating a building with `is_valid=True`.
        Expected: 201; the created building has the requesting user's id in
        validated_by.
        """
        r = self._post({**self.data, "is_valid": True})

        self.assertEqual(r.status_code, 201)
        building = Building.objects.get(rnb_id=r.json()["rnb_id"])
        self.assertEqual(building.validated_by, [self.user.id])

    def test_create_with_is_valid_false(self):
        """
        Input: POST creating a building with `is_valid=False`.
        Expected: 201; the created building has an empty validated_by.
        """
        r = self._post({**self.data, "is_valid": False})

        self.assertEqual(r.status_code, 201)
        building = Building.objects.get(rnb_id=r.json()["rnb_id"])
        self.assertEqual(building.validated_by, [])

    def test_create_without_is_valid(self):
        """
        Input: POST creating a building without the `is_valid` field.
        Expected: 201; validated_by defaults to an empty list.
        """
        r = self._post(self.data)

        self.assertEqual(r.status_code, 201)
        building = Building.objects.get(rnb_id=r.json()["rnb_id"])
        self.assertEqual(building.validated_by, [])

    def test_create_validation_unlocks_trophy(self):
        """
        Input: user already has 9 validations, POST a building with `is_valid=True`
        (the 10th validation).
        Expected: 201 with a `trophy` field {"label": "validateur", "level": 1}.
        """
        for _ in range(9):
            SummerChallenge.objects.create(
                user=self.user,
                action="validation",
                rnb_id="RNBTESTID000",
                event_id=uuid.uuid4(),
            )

        r = self._post({**self.data, "is_valid": True})

        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["trophy"], {"label": "validateur", "level": 1})

    def test_create_validation_below_threshold_no_trophy(self):
        """
        Input: POST a single building with `is_valid=True` (1st validation only).
        Expected: 201 with no `trophy` field in the response.
        """
        r = self._post({**self.data, "is_valid": True})

        self.assertEqual(r.status_code, 201)
        self.assertNotIn("trophy", r.json())
