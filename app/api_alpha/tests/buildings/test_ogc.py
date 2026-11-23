import json

from batid.models import Address, Building
from batid.tests.factories.users import ContributorUserFactory
from batid.tests.helpers import create_bdg, create_grenoble
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from freezegun import freeze_time
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class OGCEndpointsTest(APITestCase):
    def setUp(self) -> None:

        self.user = ContributorUserFactory(username="user")

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
        b.validated_by = [self.user.id]
        b.save()

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
            status="demolished",
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
                        "validated_by": [
                            {
                                "id": self.user.id,
                                "username": "user",
                                "organization_name": None,
                                "organization_short_name": None,
                            }
                        ],
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
                        "validated_by": [],
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
                        "validated_by": [
                            {
                                "id": self.user.id,
                                "username": "user",
                                "organization_name": None,
                                "organization_short_name": None,
                            }
                        ],
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

        r = self.client.get("/api/alpha/ogc/collections/buildings/items?bbox=cou,cou")
        self.assertEqual(r.status_code, 400)

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
                        "validated_by": [],
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
                        "validated_by": [],
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
                    "validated_by": [],
                },
            },
        )


class OGCBuildingItemsFiltersTest(APITestCase):
    URL = "/api/alpha/ogc/collections/buildings/items"
    BAN_ID = "fd9736e8-9970-4127-84eb-f2886043c122"
    REAL_BUILDINGS = ["BOTH", "NOTUSABLE", "UPPER"]

    def setUp(self):
        # Both spellings can coexist: cle_interop is unique with respect to case
        lower = Address.objects.create(
            cle_interop="2a004_abcd_00001", ban_id=self.BAN_ID
        )
        upper = Address.objects.create(cle_interop="2A004_ABCD_00001")

        point = GEOSGeometry("POINT(2.43 48.84)", srid=4326)
        rows = (
            ("BOTH", "constructed", True, [lower.internal_id, upper.internal_id]),
            ("UPPER", "constructed", True, [upper.internal_id]),
            ("NOTUSABLE", "notUsable", True, []),
            ("DEMOLISHED", "demolished", True, [lower.internal_id]),
            ("INACTIVE", "constructed", False, [lower.internal_id]),
        )
        for rnb_id, status, is_active, addresses in rows:
            Building.objects.create(
                rnb_id=rnb_id,
                point=point,
                shape=point,
                status=status,
                is_active=is_active,
                ext_ids=[],
                addresses_internal_id=addresses,
            )

    def _ids(self, params):
        r = self.client.get(self.URL, params)
        self.assertEqual(r.status_code, 200, r.content)
        return sorted(f["id"] for f in r.json()["features"])

    def test_filters_are_optional(self):
        """
        Input: no filter, then empty ban_id and empty cle_interop_ban.
        Expected: 200 with the active real buildings each time.
        """
        for params in ({}, {"ban_id": ""}, {"cle_interop_ban": ""}):
            with self.subTest(params=params):
                self.assertEqual(self._ids(params), self.REAL_BUILDINGS)

    def test_filter_by_ban_id(self):
        """
        Input: ban_id of an address linked to a constructed, a demolished and an
        inactive building, in several spellings; then a well-formed unknown ban_id.
        Expected: only the constructed building; no building for the unknown one.
        """
        for ban_id in (self.BAN_ID, self.BAN_ID.upper(), self.BAN_ID.replace("-", "")):
            with self.subTest(ban_id=ban_id):
                self.assertEqual(self._ids({"ban_id": ban_id}), ["BOTH"])

        unknown = "00000000-0000-4000-8000-000000000000"
        self.assertEqual(self._ids({"ban_id": unknown}), [])

    def test_ban_id_combines_with_status(self):
        """
        Input: ban_id with status=demolished, then with status=all.
        Expected: the demolished building; then all the active linked buildings.
        """
        self.assertEqual(
            self._ids({"ban_id": self.BAN_ID, "status": "demolished"}), ["DEMOLISHED"]
        )
        self.assertEqual(
            self._ids({"ban_id": self.BAN_ID, "status": "all"}), ["BOTH", "DEMOLISHED"]
        )

    def test_invalid_ban_id(self):
        """
        Input: ban_id values which are not UUIDs (text, truncated, NUL character).
        Expected: 400 on the ban_id field.
        """
        for ban_id in ("nope", self.BAN_ID[:-1], "\x00"):
            with self.subTest(ban_id=ban_id):
                r = self.client.get(self.URL, {"ban_id": ban_id})
                self.assertEqual(r.status_code, 400, r.content)
                self.assertIn("ban_id", r.json())

    def test_cle_interop_is_case_insensitive_without_duplicate(self):
        """
        Input: cle_interop_ban in lower, upper and mixed case; one building is linked
        to both spellings of the key.
        Expected: each active real building comes out exactly once.
        """
        for cle_interop in ("2a004_abcd_00001", "2A004_ABCD_00001", "2A004_aBcD_00001"):
            with self.subTest(cle_interop=cle_interop):
                self.assertEqual(
                    self._ids({"cle_interop_ban": cle_interop}), ["BOTH", "UPPER"]
                )

    def test_cle_interop_with_nul_character(self):
        """
        Input: cle_interop_ban made of, or containing, a NUL character.
        Expected: 400 on the cle_interop_ban field, not a 500.
        """
        for cle_interop in ("\x00", "abc\x00def"):
            with self.subTest(cle_interop=cle_interop):
                r = self.client.get(self.URL, {"cle_interop_ban": cle_interop})
                self.assertEqual(r.status_code, 400, r.content)
                self.assertIn("cle_interop_ban", r.json())

    def test_ban_id_and_cle_interop_are_exclusive(self):
        """
        Input: ban_id and cle_interop_ban together, then ban_id with an empty key.
        Expected: 400 naming both parameters; an empty key does not count as a filter.
        """
        r = self.client.get(
            self.URL, {"ban_id": self.BAN_ID, "cle_interop_ban": "2a004_abcd_00001"}
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json(),
            {
                "non_field_errors": [
                    "Vous devez choisir soit 'cle_interop_ban' soit 'ban_id'."
                ]
            },
        )

        self.assertEqual(
            self._ids({"ban_id": self.BAN_ID, "cle_interop_ban": ""}), ["BOTH"]
        )

    def test_status_behavior(self):
        """
        Input: the documented status values and the tolerated malformed ones, as an
        anonymous then as an authenticated user.
        Expected: 200 with the same buildings for both (no status is private);
        unknown values are ignored, nothing recognized gives no building, and an
        inactive building never comes out.
        """
        constructed = ["BOTH", "UPPER"]
        cases = {
            "constructed": constructed,
            "notUsable": ["NOTUSABLE"],
            "demolished": ["DEMOLISHED"],
            "constructed,demolished": ["BOTH", "DEMOLISHED", "UPPER"],
            "all": ["BOTH", "DEMOLISHED", "NOTUSABLE", "UPPER"],
            "constructed,unknown": constructed,
            "all,constructed": constructed,
            "constructed, demolished": constructed,
            "unknown": [],
            "CONSTRUCTED": [],
            "": [],
        }
        user = User.objects.create_user(username="ogc_status_user")
        token = Token.objects.create(user=user)

        for credentials in ({}, {"HTTP_AUTHORIZATION": f"Token {token.key}"}):
            self.client.credentials(**credentials)
            for status, expected in cases.items():
                with self.subTest(status=status, authenticated=bool(credentials)):
                    self.assertEqual(self._ids({"status": status}), expected)

    def test_openapi_exposes_filters(self):
        """
        Input: GET on the OGC OpenAPI definition.
        Expected: the items operation documents status, cle_interop_ban and ban_id
        (the latter as a UUID), all optional.
        """
        r = self.client.get("/api/alpha/ogc/openapi")
        self.assertEqual(r.status_code, 200)

        operations = [
            operation
            for path_item in json.loads(r.content)["paths"].values()
            for operation in path_item.values()
            if operation.get("operationId") == "ogcBuildingItems"
        ]
        self.assertEqual(len(operations), 1)
        params = {p["name"]: p for p in operations[0]["parameters"]}

        for name in ("status", "cle_interop_ban", "ban_id"):
            self.assertIn(name, params)
            self.assertFalse(params[name]["required"])
        self.assertEqual(params["ban_id"]["schema"]["format"], "uuid")
