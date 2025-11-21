import json

from django.contrib.gis.geos import GEOSGeometry
from freezegun import freeze_time
from rest_framework.test import APITestCase

from batid.models import Building
from batid.tests.helpers import create_bdg
from batid.tests.helpers import create_grenoble


class OGCEndpointsTest(APITestCase):
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

        b = Building.objects.create(
            rnb_id="BDGSRNBBIDID",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
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

        b = Building.objects.create(
            rnb_id="BDGPROJ",
            shape=geom,
            point=geom.point_on_surface,
            status="constructionProject",
        )

        # Check buildings in a city
        create_grenoble()
        bdg = create_bdg(
            "INGRENOBLEGO",
            [
                [5.721187072129851, 45.18439363812283],
                [5.721094925229238, 45.184330511384644],
                [5.721122483180295, 45.184274061453465],
                [5.721241326846666, 45.18428316628476],
                [5.721244771590875, 45.184325048490564],
                [5.7212697459849835, 45.18433718825423],
                [5.721187072129851, 45.18439363812283],
            ],
        )

    def test_ogc_index(self):
        r = self.client.get("/api/alpha/ogc/")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0], "application/json")

        self.maxDiff = None  # To see full diff on assertEqual failure

        self.assertEqual(
            r.json(),
            {
                "title": "Bâtiments du RNB",
                "description": "Cette API fournit les bâtiments du RNB au format OGC API Features. ",
                "links": [
                    {
                        "href": "http://testserver/api/alpha/ogc/",
                        "rel": "root",
                        "type": "application/json",
                        "title": "Racine de l'API du RNB",
                    },
                    {
                        "href": "http://testserver/api/alpha/ogc/conformance",
                        "rel": "conformance",
                        "type": "application/json",
                        "title": "Les spécifications respectées par cette API",
                    },
                    {
                        "href": "http://testserver/api/alpha/ogc/collections",
                        "rel": "data",
                        "type": "application/json",
                        "title": "Liste des types de données disponibles dans cette API",
                    },
                    {
                        "href": "http://testserver/api/alpha/ogc/openapi",
                        "rel": "service-desc",
                        "type": "application/vnd.oai.openapi+json;version=3.0",
                        "title": "Définition OpenAPI de l'API OGC du RNB",
                    },
                ],
            },
        )

    def test_ogc_conformance(self):
        r = self.client.get("/api/alpha/ogc/conformance")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            {
                "conformsTo": [
                    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
                    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
                ]
            },
        )

    def test_ogc_collections(self):
        r = self.client.get("/api/alpha/ogc/collections")
        self.assertEqual(r.status_code, 200)

        self.assertEqual(
            r.json(),
            {
                "links": [
                    {
                        "href": "http://testserver/api/alpha/ogc/collections",
                        "rel": "self",
                        "type": "application/json",
                        "title": "Liste des types de données disponibles dans cette API",
                    },
                    {
                        "href": "http://testserver/api/alpha/ogc/conformance",
                        "rel": "conformance",
                        "type": "application/json",
                        "title": "Les spécifications respectées par cette API",
                    },
                    {
                        "href": "http://testserver/api/alpha/ogc/",
                        "rel": "root",
                        "type": "application/json",
                        "title": "Racine de l'API du RNB",
                    },
                ],
                "collections": [
                    {
                        "id": "buildings",
                        "itemType": "feature",
                        "title": "Bâtiments du RNB",
                        "description": "Liste des bâtiments disponibles dans le RNB",
                        "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                        "extent": {
                            "spatial": {
                                "bbox": [[-180.0, -90.0, 180.0, 90.0]],
                                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                            }
                        },
                        "links": [
                            {
                                "href": "http://testserver/api/alpha/ogc/collections/buildings",
                                "rel": "self",
                                "type": "application/json",
                                "title": "Meta-données à propos de la liste des bâtiments disponibles dans le RNB",
                            },
                            {
                                "href": "http://testserver/api/alpha/ogc/collections/buildings/items",
                                "rel": "items",
                                "type": "application/geo+json",
                                "title": "Bâtiments disponibles dans le RNB",
                            },
                        ],
                    }
                ],
            },
        )

    def test_ogc_buildings_collection(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings")
        self.assertEqual(r.status_code, 200)

        self.assertEqual(
            r.json(),
            {
                "id": "buildings",
                "itemType": "feature",
                "title": "Bâtiments du RNB",
                "description": "Liste des bâtiments disponibles dans le RNB",
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                "extent": {
                    "spatial": {
                        "bbox": [[-180.0, -90.0, 180.0, 90.0]],
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                    }
                },
                "links": [
                    {
                        "href": "http://testserver/api/alpha/ogc/collections/buildings",
                        "rel": "self",
                        "type": "application/json",
                        "title": "Meta-données à propos de la liste des bâtiments disponibles dans le RNB",
                    },
                    {
                        "href": "http://testserver/api/alpha/ogc/collections/buildings/items",
                        "rel": "items",
                        "type": "application/geo+json",
                        "title": "Bâtiments disponibles dans le RNB",
                    },
                ],
            },
        )

    @freeze_time("2024-12-25 00:00:01", tz_offset=0)
    def test_ogc_buildings_items(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings/items")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        print(data)

        expected = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "BDGSRNBBIDID",
                    "geometry": {
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
                    "properties": {
                        "status": "constructed",
                        "ext_ids": None,
                        "addresses": [],
                        "is_active": True,
                    },
                },
                {
                    "type": "Feature",
                    "id": "INGRENOBLEGO",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [
                                [
                                    [5.721187072129851, 45.18439363812283],
                                    [5.721094925229238, 45.184330511384644],
                                    [5.721122483180295, 45.184274061453465],
                                    [5.721241326846666, 45.18428316628476],
                                    [5.721244771590875, 45.184325048490564],
                                    [5.721269745984984, 45.18433718825423],
                                    [5.721187072129851, 45.18439363812283],
                                ]
                            ]
                        ],
                    },
                    "properties": {
                        "status": "constructed",
                        "ext_ids": None,
                        "addresses": [],
                        "is_active": True,
                    },
                },
            ],
            "links": [
                {
                    "rel": "self",
                    "title": "Current page of results",
                    "href": "http://testserver/api/alpha/ogc/collections/buildings/items",
                    "type": "application/geo+json",
                }
            ],
            "numberReturned": 2,
            "timeStamp": "2024-12-25T00:00:01.000Z",
        }

        self.assertEqual(len(data["features"]), 2)
        self.assertDictEqual(data, expected)

    @freeze_time("2024-12-25 00:00:01", tz_offset=0)
    def test_ogc_buildings_items_with_limit(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings/items?limit=-1")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/ogc/collections/buildings/items?limit=200")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/ogc/collections/buildings/items?limit=coucou")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/ogc/collections/buildings/items?limit=1")
        self.assertEqual(r.status_code, 200)

        self.maxDiff = None  # To see full diff on assertEqual failure

        data = r.json()

        expected = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "BDGSRNBBIDID",
                    "geometry": {
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
                    "properties": {
                        "status": "constructed",
                        "ext_ids": None,
                        "addresses": [],
                        "is_active": True,
                    },
                },
            ],
            "links": [
                {
                    "rel": "self",
                    "title": "Current page of results",
                    "href": "http://testserver/api/alpha/ogc/collections/buildings/items?limit=1",
                    "type": "application/geo+json",
                },
                {
                    "rel": "next",
                    "title": "Next page of results",
                    "href": "http://testserver/api/alpha/ogc/collections/buildings/items?cursor=cD0x&limit=1",
                    "type": "application/geo+json",
                },
            ],
            "numberReturned": 1,
            "timeStamp": "2024-12-25T00:00:01.000Z",
        }

        self.assertEqual(len(data["features"]), 1)

        # remove query params from links as the cursor can vary depending on the tests execution order
        data["links"][1]["href"] = data["links"][1]["href"].split("?")[0]
        expected["links"][1]["href"] = expected["links"][1]["href"].split("?")[0]
        self.assertDictEqual(data, expected)

    @freeze_time("2024-12-25 00:00:01", tz_offset=0)
    def test_ogc_buildings_items_in_bbox(self):

        r = self.client.get(
            "/api/alpha/ogc/collections/buildings/items?bbox=5.7211808330356,45.18355043319679,5.722614035153486,45.18468473541278"
        )
        self.assertEqual(r.status_code, 200)

        data = r.json()

        expected = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "INGRENOBLEGO",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [
                                [
                                    [5.721187072129851, 45.18439363812283],
                                    [5.721094925229238, 45.184330511384644],
                                    [5.721122483180295, 45.184274061453465],
                                    [5.721241326846666, 45.18428316628476],
                                    [5.721244771590875, 45.184325048490564],
                                    [5.721269745984984, 45.18433718825423],
                                    [5.721187072129851, 45.18439363812283],
                                ]
                            ]
                        ],
                    },
                    "properties": {
                        "status": "constructed",
                        "ext_ids": None,
                        "addresses": [],
                        "is_active": True,
                    },
                },
            ],
            "links": [
                {
                    "rel": "self",
                    "title": "Current page of results",
                    "href": "http://testserver/api/alpha/ogc/collections/buildings/items?bbox=5.7211808330356,45.18355043319679,5.722614035153486,45.18468473541278",
                    "type": "application/geo+json",
                }
            ],
            "numberReturned": 1,
            "timeStamp": "2024-12-25T00:00:01.000Z",
        }

        data = r.json()

        self.assertEqual(len(data["features"]), 1)
        self.assertDictEqual(data, expected)

    @freeze_time("2024-12-25 00:00:01", tz_offset=0)
    def test_ogc_buildings_items_in_city(self):
        r = self.client.get(
            "/api/alpha/ogc/collections/buildings/items?insee_code=38185"
        )
        self.assertEqual(r.status_code, 200)

        data = r.json()

        expected = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "INGRENOBLEGO",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [
                                [
                                    [5.721187072129851, 45.18439363812283],
                                    [5.721094925229238, 45.184330511384644],
                                    [5.721122483180295, 45.184274061453465],
                                    [5.721241326846666, 45.18428316628476],
                                    [5.721244771590875, 45.184325048490564],
                                    [5.721269745984984, 45.18433718825423],
                                    [5.721187072129851, 45.18439363812283],
                                ]
                            ]
                        ],
                    },
                    "properties": {
                        "status": "constructed",
                        "ext_ids": None,
                        "addresses": [],
                        "is_active": True,
                    },
                },
            ],
            "links": [
                {
                    "rel": "self",
                    "title": "Current page of results",
                    "href": "http://testserver/api/alpha/ogc/collections/buildings/items?insee_code=38185",
                    "type": "application/geo+json",
                }
            ],
            "numberReturned": 1,
            "timeStamp": "2024-12-25T00:00:01.000Z",
        }

        self.assertEqual(len(data["features"]), 1)
        self.assertDictEqual(data, expected)

    def test_ogc_single_building_item(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings/items/INGRENOBLEGO")
        self.assertEqual(r.status_code, 200)

        self.assertEqual(
            r.json(),
            {
                "type": "Feature",
                "id": "INGRENOBLEGO",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [
                            [
                                [5.721187072129851, 45.18439363812283],
                                [5.721094925229238, 45.184330511384644],
                                [5.721122483180295, 45.184274061453465],
                                [5.721241326846666, 45.18428316628476],
                                [5.721244771590875, 45.184325048490564],
                                [5.721269745984984, 45.18433718825423],
                                [5.721187072129851, 45.18439363812283],
                            ]
                        ]
                    ],
                },
                "properties": {
                    "status": "constructed",
                    "ext_ids": None,
                    "addresses": [],
                    "is_active": True,
                },
            },
        )
