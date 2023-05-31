import json
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase
from batid.models import Building, BuildingStatus, User, Organization
from rest_framework.authtoken.models import Token


class BuildingsEnpointsTest(APITestCase):
    def setUp(self) -> None:
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
        geom.transform(settings.DEFAULT_SRID)

        b = Building.objects.create(
            rnb_id="BDGSRNBBIDID",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )
        BuildingStatus.objects.create(building=b, status="constructed", is_current=True)

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
        geom.transform(settings.DEFAULT_SRID)

        b = Building.objects.create(
            rnb_id="BDGPROJ",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )
        BuildingStatus.objects.create(
            building=b, status="constructionProject", is_current=True
        )

    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

        exepected = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "rnb_id": "BDGSRNBBIDID",
                    "source": "dummy",
                    "point": {
                        "type": "Point",
                        "coordinates": [1.065566769109707, 46.63416324688205],
                    },
                    "addresses": [],
                }
            ],
        }

        self.assertDictEqual(r.json(), exepected)

    def test_one_bdg_with_dash(self):
        r = self.client.get("/api/alpha/buildings/BDGS-RNBB-IDID/")
        self.assertEqual(r.status_code, 200)

        expected = {
            "rnb_id": "BDGSRNBBIDID",
            "source": "dummy",
            "point": {
                "type": "Point",
                "coordinates": [1.065566769109707, 46.63416324688205],
            },
            "addresses": [],
        }

        self.assertEqual(r.json(), expected)


class BuildingsEnpointsWithAuthTest(BuildingsEnpointsTest):
    def setUp(self):
        super().setUp()

        u = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe"
        )
        org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
        org.users.add(u)

        token = Token.objects.create(user=u)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def test_buildings_root(self):
        super().test_buildings_root()

    def test_bdg_all_signal(self):
        r = self.client.get("/api/alpha/buildings/?status=all")

        self.assertEqual(r.status_code, 200)

        expected = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "rnb_id": "BDGPROJ",
                    "source": "dummy",
                    "point": {
                        "type": "Point",
                        "coordinates": [1.065566769109707, 46.63416324688205],
                    },
                    "addresses": [],
                },
                {
                    "rnb_id": "BDGSRNBBIDID",
                    "source": "dummy",
                    "point": {
                        "type": "Point",
                        "coordinates": [1.065566769109707, 46.63416324688205],
                    },
                    "addresses": [],
                },
            ],
        }

        self.assertDictEqual(r.json(), expected)
