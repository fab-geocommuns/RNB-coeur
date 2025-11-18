import json
from unittest import mock

from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import User
from batid.models import UserProfile


class BuildingPatchTest(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        UserProfile.objects.create(user=self.user)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.rnb_id = "XXXXYYYYZZZZ"
        self.building = Building.objects.create(rnb_id=self.rnb_id)
        self.group, created = Group.objects.get_or_create(
            name=RNBContributorPermission.group_name
        )
        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

    def test_update_a_building_permission(self):
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

        self.user.groups.add(self.group)

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
        self.user.groups.add(self.group)

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
        self.user.groups.add(self.group)

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
        self.user.groups.add(self.group)

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
        self.user.groups.add(self.group)

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
        self.user.groups.add(self.group)
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
        self.assertEqual(contribution.status, "fixed")
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.review_user, self.user)
        self.assertFalse(contribution.report)

    def test_reactivate(self):
        self.assertTrue(self.building.is_active)
        c1 = Contribution.objects.create(
            rnb_id=self.building.rnb_id,
            text="ruine",
            report=True,
            status="pending",
        )
        c2 = Contribution.objects.create(
            rnb_id=self.building.rnb_id,
            text="l'adresse est fausse",
            report=True,
            status="fixed",
        )
        c3 = Contribution.objects.create(
            rnb_id=self.building.rnb_id,
            text="modif",
            report=False,
            status="fixed",
        )

        other_building = Building.create_new(
            user=self.user,
            status="constructed",
            event_origin="test",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5690889303904783, 44.83086359181351],
                                [-0.5692329185634151, 44.83090842282704],
                                [-0.5693593472030045, 44.83084615752156],
                                [-0.5691767280571298, 44.83073407980169],
                                [-0.5690889303904783, 44.83086359181351],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        c4 = Contribution.objects.create(
            rnb_id=other_building.rnb_id,
            text="l'adresse est fausse",
            report=True,
            status="pending",
        )

        # start with a deactivation
        self.building.deactivate(
            self.user, event_origin={"source": "contribution", "id": 1}
        )
        self.building.refresh_from_db()

        self.assertFalse(self.building.is_active)
        event_id_1 = self.building.event_id
        self.assertTrue(event_id_1 is not None)
        self.assertEqual(self.building.event_type, "deactivation")
        c1.refresh_from_db()
        c2.refresh_from_db()
        c3.refresh_from_db()
        c4.refresh_from_db()
        # updated contribution
        self.assertEqual(c1.status, "refused")
        # this is how the link is done
        self.assertEqual(c1.status_updated_by_event_id, self.building.event_id)
        # untouched contributions
        self.assertEqual(c2.status, "fixed")
        self.assertEqual(c3.status, "fixed")
        self.assertEqual(c4.status, "pending")

        # then reactivate
        self.building.reactivate(self.user, {"source": "contribution", "id": 2})
        self.building.refresh_from_db()

        self.assertTrue(self.building.is_active)
        event_id_2 = self.building.event_id
        self.assertTrue(event_id_2 is not None)
        self.assertNotEqual(event_id_1, event_id_2)
        self.assertEqual(self.building.event_type, "reactivation")
        # signalements (reports) closed by deactivation are reset to "pending"
        c1.refresh_from_db()
        c2.refresh_from_db()
        c3.refresh_from_db()
        c4.refresh_from_db()

        # reset contribution status
        self.assertEqual(c1.status, "pending")
        self.assertIsNone(c1.status_changed_at)
        self.assertIsNone(c1.status_updated_by_event_id)
        self.assertIsNone(c1.review_user)
        self.assertIsNone(c1.review_comment)
        # untouched contributions
        self.assertEqual(c2.status, "fixed")
        self.assertEqual(c3.status, "fixed")
        self.assertEqual(c4.status, "pending")

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

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_update_building(self):
        self.user.groups.add(self.group)
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
        self.assertEqual(contribution.status, "fixed")
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.review_user, self.user)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_update_building_duplicate_address(self):
        self.user.groups.add(self.group)
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
        self.assertEqual(contribution.status, "fixed")
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.review_user, self.user)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_update_with_empty_addresses(self):
        self.user.groups.add(self.group)

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

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_update_building_shape_hex(self):
        self.user.groups.add(self.group)
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

    def test_update_building_shape_point(self):
        self.user.groups.add(self.group)
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

        self.user.groups.add(self.group)
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

        self.user.groups.add(self.group)
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

        self.user.groups.add(self.group)
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

        self.user.groups.add(self.group)
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
        self.user.groups.add(self.group)

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

        self.assertEqual(r.status_code, 429)

        # Verify the building was not updated
        self.building.refresh_from_db()
        self.assertNotEqual(self.building.event_type, "update")
        self.assertNotEqual(self.building.status, "notUsable")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)

    def test_deactivate_building_contribution_limit_exceeded(self):
        self.user.groups.add(self.group)

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

        self.assertEqual(r.status_code, 429)

        # Verify the building was not deactivated
        self.building.refresh_from_db()
        self.assertTrue(self.building.is_active)
        self.assertNotEqual(self.building.event_type, "deactivation")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)
