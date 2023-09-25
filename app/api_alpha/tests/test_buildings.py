import datetime
import json
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase
from batid.models import Building, BuildingStatus, User, Organization
from rest_framework.authtoken.models import Token


class BuildingsEndpointsTest(APITestCase):
    def setUp(self) -> None:
        self.maxDiff = None

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
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

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
            building=b,
            type="constructionProject",
            is_current=True,
            happened_at=datetime.datetime(2020, 2, 1),
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
                    "status": [
                        {
                            "type": "constructed",
                            "label": "Construit",
                            "happened_at": None,
                            "is_current": True,
                        }
                    ],
                    "point": {
                        "type": "Point",
                        "coordinates": [1.065566769109709, 46.63416324688213],
                    },
                    "addresses": [],
                }
            ],
        }

        self.assertDictEqual(r.json(), exepected)

    def test_one_bdg_with_dash(self):
        # r = self.client.get("/api/alpha/buildings/BDGS-RNBB-IDID/")
        r = self.client.get("/api/alpha/buildings/BDGSRNBBIDID/")
        self.assertEqual(r.status_code, 200)

        expected = {
            "rnb_id": "BDGSRNBBIDID",
            "point": {
                "type": "Point",
                "coordinates": [1.065566769109709, 46.63416324688213],
            },
            "status": [
                {
                    "type": "constructed",
                    "label": "Construit",
                    "happened_at": None,
                    "is_current": True,
                }
            ],
            "addresses": [],
        }

        self.assertEqual(r.json(), expected)


class BuildingsEndpointsWithAuthTest(BuildingsEndpointsTest):
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
        data = r.json()

        self.assertEqual(r.status_code, 200)

        expected = [
            {
                "ext_bdtopo_id": None,
                "rnb_id": "BDGSRNBBIDID",
                "point": {
                    "type": "Point",
                    "coordinates": [1.065566769109709, 46.63416324688213],
                },
                "status": [
                    {
                        "type": "constructed",
                        "label": "Construit",
                        "happened_at": None,
                        "is_current": True,
                    }
                ],
                "addresses": [],
            },
            {
                "ext_bdtopo_id": None,
                "rnb_id": "BDGPROJ",
                "point": {
                    "type": "Point",
                    "coordinates": [1.065566769109709, 46.63416324688213],
                },
                "status": [
                    {
                        "type": "constructionProject",
                        "label": "En projet",
                        "is_current": True,
                        "happened_at": "2020-02-01",
                    }
                ],
                "addresses": [],
            },
        ]

        self.assertEqual(len(data), 2)
        self.maxDiff = None
        self.assertListEqual(data, expected)


class BuildingsEndpointsSingleTest(APITestCase):
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
            rnb_id="SINGLEONE",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )
        BuildingStatus.objects.create(
            building=b,
            type="constructed",
            happened_at=datetime.datetime(2020, 2, 1),
        )
        BuildingStatus.objects.create(
            building=b,
            type="constructionProject",
        )
        BuildingStatus.objects.create(
            building=b,
            type="demolished",
            is_current=True,
            happened_at=datetime.datetime(2022, 2, 1),
        )

    def test_status_order(self):
        r = self.client.get("/api/alpha/buildings/SINGLEONE/")
        self.assertEqual(r.status_code, 200)

        status = r.json()["status"]

        self.assertEqual(status[0]["type"], "constructionProject")
        self.assertEqual(status[1]["type"], "constructed")
        self.assertEqual(status[2]["type"], "demolished")
