import json

from batid.models import Address, Building, Plot
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase


class SingleBuildingTest(APITestCase):
    def setUp(self):

        u1 = User.objects.create_user(username="u1", email="u1@test.com")
        u2 = User.objects.create_user(username="u2", email="u2@test.com")

        Address.objects.create(
            id="addr-1",
            source="bdnb",
            street_number="3",
            street_rep="",
            street="rue de l'eglise",
            city_name="Chivy-lès-Étouvelles",
            city_zipcode="02000",
            city_insee_code="02191",
        )

        coords = {
            "coordinates": [
                [
                    [
                        [1.0654705955877262, 46.63423852982024],
                        [1.065454930919401, 46.634105152847496],
                        [1.0656648374661017, 46.63409009413692],
                        [1.0656773692001593, 46.63422131990677],
                        [1.0654705955877262, 46.63423852982024],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)

        Building.objects.create(
            rnb_id="1234ABCD5678",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            addresses_id=["addr-1"],
            ext_ids=[
                {
                    "source": "bdnb",
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                    "source_version": "25",
                }
            ],
            marked_as_correct_by=[u1.id, u2.id],
        )

        Plot.objects.create(id="plot-1", shape=geom)

    def test_single_bdg(self):

        r = self.client.get("/api/alpha/buildings/1234ABCD5678/")
        self.assertEqual(r.status_code, 200)

        expected = {
            "rnb_id": "1234ABCD5678",
            "status": "constructed",
            "point": {
                "type": "Point",
                "coordinates": [1.065566787499344, 46.634163236377134],
            },
            "shape": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [1.065470595587726, 46.63423852982024],
                            [1.065454930919401, 46.634105152847496],
                            [1.065664837466102, 46.63409009413692],
                            [1.065677369200159, 46.63422131990677],
                            [1.065470595587726, 46.63423852982024],
                        ]
                    ]
                ],
            },
            "addresses": [
                {
                    "id": "addr-1",
                    "ban_id": None,
                    "source": "bdnb",
                    "street_number": "3",
                    "street_rep": "",
                    "street": "rue de l'eglise",
                    "city_name": "Chivy-lès-Étouvelles",
                    "city_zipcode": "02000",
                    "city_insee_code": "02191",
                }
            ],
            "ext_ids": [
                {
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "source": "bdnb",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                    "source_version": "25",
                }
            ],
            "is_active": True,
            "marked_as_correct_by": [
                {
                    "display_name": "u1",
                    "id": User.objects.get(username="u1").id,
                    "username": "u1",
                },
                {
                    "display_name": "u2",
                    "id": User.objects.get(username="u2").id,
                    "username": "u2",
                },
            ],
        }

        self.assertDictEqual(r.data, expected)

    def test_single_bdg_geojson(self):

        r = self.client.get("/api/alpha/buildings/1234ABCD5678/?format=geojson")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["type"], "Feature")
        self.assertEqual(r.data["id"], "1234ABCD5678")
        self.assertEqual(r.data["geometry"]["type"], "MultiPolygon")
        self.assertEqual(r.data["properties"]["status"], "constructed")
        self.assertEqual(r.data["properties"]["is_active"], True)

        self.assertListEqual(
            list(r.data["properties"]["marked_as_correct_by"][0].keys()),
            ["display_name", "id", "username"],
        )
        self.assertEqual(
            r.data["properties"]["marked_as_correct_by"][0]["display_name"], "u1"
        )
        self.assertEqual(
            r.data["properties"]["marked_as_correct_by"][0]["username"], "u1"
        )

        self.assertEqual(
            r.data["properties"]["marked_as_correct_by"][1]["display_name"], "u2"
        )
        self.assertEqual(
            r.data["properties"]["marked_as_correct_by"][1]["username"], "u2"
        )

        self.assertListEqual(
            r.data["properties"]["ext_ids"],
            [
                {
                    "source": "bdnb",
                    "source_version": "25",
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                }
            ],
        )
        self.assertListEqual(
            r.data["properties"]["addresses"],
            [
                {
                    "id": "addr-1",
                    "ban_id": None,
                    "source": "bdnb",
                    "street_number": "3",
                    "street_rep": "",
                    "street": "rue de l'eglise",
                    "city_name": "Chivy-lès-Étouvelles",
                    "city_zipcode": "02000",
                    "city_insee_code": "02191",
                }
            ],
        )

        self.assertNotIn("plots", r.data["properties"])

    def test_single_bdg_geojson_w_plots(self):

        r = self.client.get(
            "/api/alpha/buildings/1234ABCD5678/?format=geojson&withPlots=1"
        )

        self.assertIn("plots", r.data["properties"])
        self.assertListEqual(
            r.data["properties"]["plots"],
            [{"id": "plot-1", "bdg_cover_ratio": 1}],
        )

    def test_single_none_marked_as_correct_by(self):

        b = Building.objects.get(rnb_id="1234ABCD5678")
        b.marked_as_correct_by = None
        b.save()

        r = self.client.get("/api/alpha/buildings/1234ABCD5678/")
        self.assertEqual(r.status_code, 200)

        self.assertEqual(r.data["marked_as_correct_by"], [])
