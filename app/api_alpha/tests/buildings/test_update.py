import json
import uuid
from unittest import mock

from batid.models import Address, Building, Contribution, SummerChallenge
from batid.tests.factories.users import ContributorUserFactory
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class BuildingPatchTest(APITestCase):
    def setUp(self) -> None:
        self.user = ContributorUserFactory(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.rnb_id = "XXXXYYYYZZZZ"
        self.building = Building.objects.create(
            rnb_id=self.rnb_id, shape=GEOSGeometry("POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))")
        )
        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

    def test_update_a_building_permission(self):
        self.user.groups.clear()

        data = {
            "is_active": False,
            "comment": "ce n'est pas un batiment, mais un bosquet",
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

    def test_update_a_building(self):

        data = {
            "is_active": False,
            "comment": "ce n'est pas un batiment, mais un bosquet",
        }

        # deactivate the user
        self.user.is_active = False
        self.user.save()

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # unauthorized!
        self.assertEqual(r.status_code, 401)

        # activate the user
        self.user.is_active = True
        self.user.save()

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

    def test_update_empty_shape(self):
        data = {
            "shape": "POlYGON EMPTY",
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json(),
            {"shape": ["La forme fournie est vide"]},
        )

    def test_update_a_building_invalid_shape(self):
        data = {
            "shape": "POLYGON ((1000 0, 1000 1, 1001 1, 1001 0, 1000 0))",
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "La géométrie n'est pas valide",
            r.json()["detail"],
        )

    def test_update_a_building_parameters(self):
        # empty data
        data = {}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # update status ok
        data = {"status": "demolished", "comment": "démoli"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

        # not a building
        data = {"is_active": False, "comment": "not a building"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

    def test_update_a_building_parameters_2(self):
        # update status : unauthorized status
        data = {"status": "painted_black", "comment": "peint en noir"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # update status and addresses
        data = {
            "status": "constructed",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
            "comment": "mise à jour status et adresses",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

        # comment is not mandatory
        data = {
            "status": "constructed",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
            "comment": "",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 204)

        data = {
            "status": "constructed",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 204)

        # can either deactivate or update
        data = {
            "is_active": False,
            "status": "demolished",
            "comment": "je fais nimp je suis un fou",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_deactivate(self):
        comment = "not a building"
        data = {"is_active": False, "comment": comment}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        contributions = Contribution.objects.all()
        contribution = contributions[0]

        self.assertEqual(self.building.event_type, "deactivation")
        self.assertEqual(
            self.building.event_origin,
            {"source": "contribution", "contribution_id": contribution.id},
        )
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.user, self.user)

    def test_cannot_reactivate_everything(self):
        with self.assertRaises(Exception) as e:
            # the building is active
            self.building.reactivate()

        # now we set the building as if it has been deactivated during a merge
        self.building.event_type = "merge"
        self.building.is_active = False
        self.building.save()

        with self.assertRaises(Exception) as e:
            # not active, but not deactivated by a "deactivation" event
            self.building.reactivate()

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_update_building(self):
        comment = "maj du batiment"
        data = {
            "status": "notUsable",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        contributions = Contribution.objects.all()
        contribution = contributions[0]

        self.assertEqual(self.building.event_type, "update")
        self.assertEqual(self.building.status, "notUsable")
        self.assertCountEqual(self.building.addresses_id, [self.adr1.id, self.adr2.id])
        self.assertEqual(
            self.building.event_origin,
            {"source": "contribution", "contribution_id": contribution.id},
        )
        g = GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        self.assertEqual(self.building.shape.wkt, g.wkt)
        self.assertTrue(g.contains(self.building.point))
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.user, self.user)

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_update_building_duplicate_address(self):
        comment = "maj du batiment"
        data = {
            "status": "notUsable",
            "addresses_cle_interop": [self.adr1.id, self.adr1.id],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        contributions = Contribution.objects.all()
        contribution = contributions[0]

        self.assertEqual(self.building.event_type, "update")
        self.assertEqual(self.building.status, "notUsable")
        self.assertEqual(self.building.addresses_id, [self.adr1.id])
        self.assertEqual(
            self.building.event_origin,
            {"source": "contribution", "contribution_id": contribution.id},
        )
        g = GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        self.assertEqual(self.building.shape.wkt, g.wkt)
        self.assertTrue(g.contains(self.building.point))
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.user, self.user)

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_update_with_empty_addresses(self):

        # First, we have to add some addresses to the building
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1", "cle_interop_2"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 204)

        self.building.refresh_from_db()

        # We check that the addresses have been added
        expected_addresses = ["cle_interop_1", "cle_interop_2"]
        expected_addresses.sort()

        self.building.addresses_id.sort()

        self.assertListEqual(self.building.addresses_id, expected_addresses)

        # We can now remove all addresses
        data = {
            "shape": self.building.shape.json,
            "status": self.building.status,
            "addresses_cle_interop": [],
            "comment": "maj du batiment avec des adresses vides",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()

        self.assertListEqual(self.building.addresses_id, [])

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_update_building_shape_hex(self):
        comment = "maj du batiment"
        wkt = "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))"
        g = GEOSGeometry(wkt)
        data = {
            "shape": g.hex.decode(),
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()

        self.assertEqual(self.building.shape.wkt, wkt)
        self.assertTrue(g.contains(self.building.point))

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_update_building_shape_point(self):
        comment = "maj du batiment"
        wkt = "POINT (1 1)"
        g = GEOSGeometry(wkt)
        data = {
            "shape": g.wkt,
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()

        self.assertEqual(self.building.shape.wkt, wkt)
        self.assertEqual(self.building.point, self.building.shape)

    @mock.patch("batid.models.requests.get")
    def test_new_address(self, get_mock):
        get_mock.return_value.status_code = 200
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "type": "numero",
            "numero": 12,
            "suffixe": "bis",
            "lon": -0.581012,
            "lat": 44.845842,
            "codePostal": "33000",
            "cleInterop": cle_interop,
            "voie": {
                "nomVoie": "Rue Turenne",
            },
            "commune": {
                "nom": "Bordeaux",
                "code": "33063",
            },
        }

        comment = "maj du batiment avec une adresse BAN toute fraiche"
        data = {
            "addresses_cle_interop": [cle_interop],
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

        address = Address.objects.get(id=cle_interop)

        self.assertEqual(address.source, "ban")
        self.assertEqual(address.point.wkt, "POINT (-0.581012 44.845842)")
        self.assertEqual(address.street_number, "12")
        self.assertEqual(address.street_rep, "bis")
        self.assertEqual(address.street, "Rue Turenne")
        self.assertEqual(address.city_name, "Bordeaux")
        self.assertEqual(address.city_zipcode, "33000")
        self.assertEqual(address.city_insee_code, "33063")

    @mock.patch("batid.models.requests.get")
    def test_new_address_BAN_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        comment = "maj du batiment avec une adresse BAN toute fraiche"
        data = {
            "addresses_cle_interop": [cle_interop],
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 503)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @mock.patch("batid.models.requests.get")
    def test_new_address_BAN_unknown_id(self, get_mock):
        get_mock.return_value.status_code = 404
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "what is this id?",
        }

        comment = "maj du batiment avec une adresse BAN toute fraiche"
        data = {
            "addresses_cle_interop": [cle_interop],
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @mock.patch("batid.models.requests.get")
    def test_new_address_not_good_type(self, get_mock):
        get_mock.return_value.status_code = 200
        cle_interop = "33063_9115"
        get_mock.return_value.json.return_value = {
            "type": "rue",
            "numero": "",
            "suffixe": "",
            "lon": -0.581012,
            "lat": 44.845842,
            "codePostal": "33000",
            "cleInterop": cle_interop,
            "voie": {
                "nomVoie": "Rue Turenne",
            },
            "commune": {
                "nom": "Bordeaux",
                "code": "33063",
            },
        }

        comment = "maj du batiment avec une adresse de type voie"
        data = {
            "addresses_cle_interop": [cle_interop],
            "comment": comment,
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_update_building_contribution_limit_exceeded(self):
        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        data = {
            "status": "notUsable",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "maj du batiment",
        }

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

        # Verify the building was not updated
        self.building.refresh_from_db()
        self.assertNotEqual(self.building.event_type, "update")
        self.assertNotEqual(self.building.status, "notUsable")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_update_building_contribution_limit_exceeded_but_sandbox(self):

        with self.settings(ENVIRONMENT="sandbox"):

            # Set user to have reached their contribution limit
            self.user.profile.total_contributions = 500
            self.user.profile.max_allowed_contributions = 500
            self.user.profile.save()

            data = {
                "status": "notUsable",
                "addresses_cle_interop": [self.adr1.id, self.adr2.id],
                "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                "comment": "maj du batiment",
            }

            r = self.client.patch(
                f"/api/alpha/buildings/{self.rnb_id}/",
                data=json.dumps(data),
                content_type="application/json",
            )

            self.assertEqual(r.status_code, 204)

            # Verify the building was updated
            self.building.refresh_from_db()
            self.assertEqual(self.building.event_type, "update")
            self.assertEqual(self.building.status, "notUsable")

            # Verify user contribution count did increase
            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.total_contributions, 501)

    def test_deactivate_building_contribution_limit_exceeded(self):

        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        comment = "not a building"
        data = {"is_active": False, "comment": comment}

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

        # Verify the building was not deactivated
        self.building.refresh_from_db()
        self.assertTrue(self.building.is_active)
        self.assertNotEqual(self.building.event_type, "deactivation")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)

    def test_deactivate_building_contribution_limit_exceeded_but_sandbox(self):

        with self.settings(ENVIRONMENT="sandbox"):

            # Set user to have reached their contribution limit
            self.user.profile.total_contributions = 500
            self.user.profile.max_allowed_contributions = 500
            self.user.profile.save()

            comment = "not a building"
            data = {"is_active": False, "comment": comment}

            r = self.client.patch(
                f"/api/alpha/buildings/{self.rnb_id}/",
                data=json.dumps(data),
                content_type="application/json",
            )

            self.assertEqual(r.status_code, 204)

            # Verify the building was deactivated
            self.building.refresh_from_db()
            self.assertFalse(self.building.is_active)
            self.assertEqual(self.building.event_type, "deactivation")

            # Verify user contribution count did increase
            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.total_contributions, 501)


class BuildingPatchValidateTest(APITestCase):
    """Tests for the `validate` parameter on PATCH /api/alpha/buildings/<rnb_id>/."""

    def setUp(self) -> None:
        self.user = ContributorUserFactory(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        self.other_user = ContributorUserFactory(username="other")
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.rnb_id = "XXXXYYYYZZZZ"
        self.building = Building.objects.create(
            rnb_id=self.rnb_id,
            status="constructed",
            shape=GEOSGeometry("POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))"),
            validated_by=[],
        )

    def test_is_valid_true_alone(self):
        """
        Input: PATCH with only `is_valid=True`, building's validated_by is empty.
        Expected: 204; the requesting user's id is appended to validated_by;
        a Contribution with status='fixed' is created and linked to the user.
        """
        data = {"is_valid": True, "comment": "ce bâtiment est correct"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        self.assertEqual(self.building.validated_by, [self.user.id])

        contribution = Contribution.objects.get(rnb_id=self.rnb_id)
        self.assertEqual(contribution.user, self.user)
        self.assertEqual(contribution.text, "ce bâtiment est correct")

    def test_is_valid_false_removes_user(self):
        """
        Input: building has the requesting user already in validated_by; PATCH
        with only `is_valid=False`.
        Expected: 204; user.id is removed from validated_by.
        """
        self.building.validated_by = [self.user.id, self.other_user.id]
        self.building.save()

        data = {"is_valid": False}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        self.assertEqual(self.building.validated_by, [self.other_user.id])

    def test_validate_false_idempotent_when_user_absent(self):
        """
        Input: building's validated_by does not contain the requesting user;
        PATCH with only `is_valid=False`.
        Expected: 204 (no ValueError); validated_by stays unchanged.
        """
        self.building.validated_by = [self.other_user.id]
        self.building.save()

        data = {"is_valid": False}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        self.assertEqual(self.building.validated_by, [self.other_user.id])

    def test_is_valid_true_with_status_change_resets_list_and_adds_user(self):
        """
        Input: building already has another user in validated_by; PATCH with
        `is_valid=True` AND a new `status`.
        Expected: 204; previous marks are cleared because the building changed, then
        the requesting user is appended — final list is [self.user.id]; status updated.
        """
        self.building.validated_by = [self.other_user.id]
        self.building.save()

        data = {
            "status": "demolished",
            "is_valid": True,
            "comment": "démoli et je confirme",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
        self.building.refresh_from_db()
        self.assertEqual(self.building.status, "demolished")
        self.assertEqual(self.building.validated_by, [self.user.id])

    def test_is_valid_with_is_active_rejected(self):
        """
        Input: PATCH combining `is_valid=True` with `is_active=False`.
        Expected: 400 (validation error) — both fields are mutually exclusive; the
        building stays untouched.
        """
        data = {
            "is_active": False,
            "is_valid": True,
            "comment": "incompatible",
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.building.refresh_from_db()
        self.assertTrue(self.building.is_active)
        self.assertEqual(self.building.validated_by, [])

    def test_is_valid_null_rejected(self):
        """
        Input: PATCH with `is_valid=None` (JSON null).
        Expected: 400 — the serializer's BooleanField does not allow null
        (no `allow_null=True`); building stays untouched.
        """
        data = {"is_valid": None}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.building.refresh_from_db()
        self.assertEqual(self.building.validated_by, [])

    def test_validation_unlocks_trophy(self):
        """
        Input: user already has 9 validations; PATCH with `is_valid=True`
        (the 10th validation).
        Expected: 200 with body {"trophy": {"label": "validateur", "level": 1}}.
        """
        for _ in range(9):
            SummerChallenge.objects.create(
                user=self.user,
                action="validation",
                rnb_id="RNBTESTID000",
                event_id=uuid.uuid4(),
            )

        data = {"is_valid": True, "comment": "ok"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"trophy": {"label": "validateur", "level": 1}})

    def test_validation_below_threshold_returns_204(self):
        """
        Input: PATCH with `is_valid=True` (1st validation, below the 10 threshold).
        Expected: 204 with no body.
        """
        data = {"is_valid": True, "comment": "ok"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)
