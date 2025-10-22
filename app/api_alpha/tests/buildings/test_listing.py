import json

from django.contrib.gis.geos import GEOSGeometry
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import Address
from batid.models import Building
from batid.models import Organization
from batid.models import Plot
from batid.models import User
from batid.tests.helpers import create_bdg
from batid.tests.helpers import create_grenoble


class BuildingsEndpointsTest(APITestCase):
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

    def test_bdg_in_bbox(self):

        r = self.client.get(
            "/api/alpha/buildings/?bbox=5.7211808330356,45.18355043319679,5.722614035153486,45.18468473541278"
        )
        self.assertEqual(r.status_code, 200)

        expected = {
            "previous": None,
            "next": None,
            "results": [
                {
                    "addresses": [],
                    "ext_ids": None,
                    "status": "constructed",
                    "point": {
                        "coordinates": [5.721181338205954, 45.18433384981944],
                        "type": "Point",
                    },
                    "shape": {
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
                    "rnb_id": "INGRENOBLEGO",
                    "is_active": True,
                }
            ],
        }

        data = r.json()

        self.assertEqual(len(data["results"]), 1)
        self.assertDictEqual(data, expected)

    def test_bdg_in_bbox_with_negative_lon(self):
        r = self.client.get("/api/alpha/buildings/?bbox=-1.0,45.845782,-0.5,46.0")
        self.assertEqual(r.status_code, 200)

    def test_bdg_in_bbox_invalid_lat(self):
        r = self.client.get("/api/alpha/buildings/?bbox=-1.0,45.845782,-0.5,coucou")
        self.assertEqual(r.status_code, 400)

    def test_bdg_in_bbox_too_big(self):
        r = self.client.get(
            "/api/alpha/buildings/?bbox=5.7211808330356,45.18355043319679,8.722614035153486,47.18468473541278"
        )
        self.assertEqual(r.status_code, 400)
        data = r.json()
        self.assertDictEqual(
            data,
            {
                "bbox": [
                    "La bbox est trop grande, (max_lon - min_lon) * (max_lat - min_lat) doit être inférieur à 4. Si vous avez besoin de bbox plus grandes, merci de nous contacter."
                ]
            },
        )

    def test_bdg_in_bbox_obsolote(self):

        # This test uses the legacy "bb" parameter which is now marked as obsolete in the API documentation

        r = self.client.get(
            "/api/alpha/buildings/?bb=45.18468473541278,5.7211808330356,45.18355043319679,5.722614035153486"
        )
        self.assertEqual(r.status_code, 200)

        expected = {
            "previous": None,
            "next": None,
            "results": [
                {
                    "addresses": [],
                    "ext_ids": None,
                    "status": "constructed",
                    "point": {
                        "coordinates": [5.721181338205954, 45.18433384981944],
                        "type": "Point",
                    },
                    "shape": {
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
                    "rnb_id": "INGRENOBLEGO",
                    "is_active": True,
                }
            ],
        }

        data = r.json()

        self.assertEqual(len(data["results"]), 1)
        self.assertDictEqual(data, expected)

    def test_bdg_in_obsolete_bbox_too_big(self):
        r = self.client.get(
            "/api/alpha/buildings/?bb=48.18468473541278,5.7211808330356,45.18355043319679,7.722614035153486"
        )
        self.assertEqual(r.status_code, 400)
        data = r.json()
        self.assertDictEqual(
            data,
            {
                "bb": [
                    "La bounding box est trop grande, (se_lon - nw_lon) * (nw_lat - se_lat) doit être inférieur à 4."
                ]
            },
        )

    def test_bdg_in_city(self):
        r = self.client.get("/api/alpha/buildings/?insee_code=38185")
        self.assertEqual(r.status_code, 200)

        expected = {
            "previous": None,
            "next": None,
            "results": [
                {
                    "addresses": [],
                    "ext_ids": None,
                    "status": "constructed",
                    "point": {
                        "coordinates": [5.721181338205954, 45.18433384981944],
                        "type": "Point",
                    },
                    "shape": {
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
                    "rnb_id": "INGRENOBLEGO",
                    "is_active": True,
                }
            ],
        }

        data = r.json()

        self.assertEqual(len(data["results"]), 1)
        self.assertDictEqual(data, expected)

        building = Building.objects.get(rnb_id="INGRENOBLEGO")
        building.is_active = False
        building.save()

        r = self.client.get("/api/alpha/buildings/?insee_code=38185")
        # No building should be returned
        self.assertEqual(len(r.json()["results"]), 0)

    def test_bdg_with_cle_interop_ban(self):
        cle_interop_ban = "33522_2620_00021"
        Address.objects.create(id=cle_interop_ban)
        Address.objects.create(id="123")

        bdg = Building.objects.create(
            rnb_id="XXX",
            point=GEOSGeometry("POINT(0 0)"),
            addresses_id=[cle_interop_ban],
        )

        # other buildings
        Building.objects.create(rnb_id="YYY", addresses_id=["123"])
        Building.objects.create(rnb_id="ZZZ", addresses_id=[])

        r = self.client.get(f"/api/alpha/buildings/?cle_interop_ban={cle_interop_ban}")
        self.assertEqual(r.status_code, 200)

        expected = {
            "previous": None,
            "next": None,
            "results": [
                {
                    "addresses": [
                        {
                            "id": "33522_2620_00021",
                            "source": "",
                            "street_number": None,
                            "street_rep": None,
                            "street": None,
                            "city_name": None,
                            "city_zipcode": None,
                            "city_insee_code": None,
                        }
                    ],
                    "ext_ids": None,
                    "status": "constructed",
                    "point": {
                        "coordinates": [0.0, 0.0],
                        "type": "Point",
                    },
                    "shape": None,
                    "rnb_id": "XXX",
                    "is_active": True,
                }
            ],
        }

        data = r.json()

        self.assertEqual(len(data["results"]), 1)
        self.assertDictEqual(data, expected)

        bdg.is_active = False
        bdg.save()

        r = self.client.get(f"/api/alpha/buildings/?cle_interop_ban={cle_interop_ban}")
        # No building should be returned
        self.assertEqual(len(r.json()["results"]), 0)

    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

        expected = {
            "previous": None,
            "next": None,
            "results": [
                {
                    "ext_ids": None,
                    "status": "constructed",
                    "rnb_id": "BDGSRNBBIDID",
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
                    "addresses": [],
                    "is_active": True,
                },
                {
                    "addresses": [],
                    "ext_ids": None,
                    "status": "constructed",
                    "point": {
                        "coordinates": [5.721181338205954, 45.18433384981944],
                        "type": "Point",
                    },
                    "shape": {
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
                    "rnb_id": "INGRENOBLEGO",
                    "is_active": True,
                },
            ],
        }

        self.assertDictEqual(r.json(), expected)

    def test_buildings_root_geojson(self):

        r = self.client.get("/api/alpha/buildings/?format=geojson")
        self.assertEqual(r.status_code, 200)

        self.maxDiff = None

        data = r.json()
        self.assertEqual(data["type"], "FeatureCollection")

        response_timestamp = data["timeStamp"]

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
                    "href": "http://testserver/api/alpha/buildings/?format=geojson",
                    "type": "application/geo+json",
                }
            ],
            "numberReturned": 2,
            "timeStamp": response_timestamp,  # response timestamp is dynamic, we just check its presence
        }

        self.assertDictEqual(data, expected)

    def test_one_bdg_with_dash(self):
        r = self.client.get("/api/alpha/buildings/BDGS-RNBB-IDID/")
        # r = self.client.get("/api/alpha/buildings/BDGSRNBBIDID/")
        self.assertEqual(r.status_code, 200)

        expected = {
            "ext_ids": None,
            "rnb_id": "BDGSRNBBIDID",
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
            "addresses": [],
            "is_active": True,
        }

        self.assertEqual(r.json(), expected)

    def test_non_active_buildings_are_excluded_from_list(self):
        building = Building.objects.get(rnb_id="BDGSRNBBIDID")

        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["results"]), 2)

        building.is_active = False
        building.save()

        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["results"]), 1)

    def test_non_active_building_individual_request_ok(self):
        Building.objects.create(
            rnb_id="XXXXYYYYZZZZ", point=GEOSGeometry("POINT (0 0)"), is_active=False
        )
        r = self.client.get("/api/alpha/buildings/XXXXYYYYZZZZ/")
        self.assertEqual(r.status_code, 200)
        result = r.json()
        self.assertEqual(result["is_active"], False)


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

        expected = {
            "previous": None,
            "next": None,
            "results": [
                {
                    "ext_ids": None,
                    "rnb_id": "BDGSRNBBIDID",
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
                    "addresses": [],
                    "is_active": True,
                },
                {
                    "ext_ids": None,
                    "rnb_id": "BDGPROJ",
                    "status": "constructionProject",
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
                    "addresses": [],
                    "is_active": True,
                },
                {
                    "addresses": [],
                    "ext_ids": None,
                    "status": "constructed",
                    "point": {
                        "coordinates": [5.721181338205954, 45.18433384981944],
                        "type": "Point",
                    },
                    "shape": {
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
                    "rnb_id": "INGRENOBLEGO",
                    "is_active": True,
                },
            ],
        }

        self.assertEqual(len(data["results"]), 3)
        self.assertDictEqual(data, expected)


class BuildingsWithPlots(APITestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bdg_one = None
        self.bdg_two = None

    def setUp(self):
        # The two plots are side by side

        user = User.objects.create_user(username="user")

        Plot.objects.create(
            id="one",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [
                                    [0.9105774090996306, 44.84936803275076],
                                    [0.9102857535320368, 44.84879419445585],
                                    [0.9104349726604539, 44.84847040607977],
                                    [0.9109969204173751, 44.848225799624316],
                                    [0.9112463293299982, 44.84857273425834],
                                    [0.9113505129542716, 44.84894428770244],
                                    [0.9113883978533295, 44.84920168780678],
                                    [0.9105774090996306, 44.84936803275076],
                                ]
                            ]
                        ],
                        "type": "MultiPolygon",
                    }
                ),
                srid=4326,
            ),
        )

        Plot.objects.create(
            id="two",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [
                                    [0.910571664716457, 44.84936946559145],
                                    [0.9103209027180412, 44.84944151365943],
                                    [0.9100424249191121, 44.84885483391221],
                                    [0.9102799889177788, 44.84879588489878],
                                    [0.910571664716457, 44.84936946559145],
                                ]
                            ]
                        ],
                        "type": "MultiPolygon",
                    }
                ),
                srid=4326,
            ),
        )

        self.bdg_one = Building.create_new(
            user=user,
            event_origin={"dummy": "dummy"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [0.9104005886575237, 44.84928501664322],
                                [0.9102901511915604, 44.84910387339187],
                                [0.9105699884996739, 44.84904017453093],
                                [0.910669195036661, 44.84922264503825],
                                [0.9104005886575237, 44.84928501664322],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        self.bdg_two = Building.create_new(
            user=user,
            event_origin={"dummy": "dummy"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [0.9101392761545242, 44.849463423418655],
                                [0.9103279421314028, 44.849432783031574],
                                [0.9103827965568883, 44.84963842685542],
                                [0.9101484185592597, 44.84964255150933],
                                [0.9101392761545242, 44.849463423418655],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

    def test_with_plots(self):

        expected_w_plots = {
            "next": None,
            "previous": None,
            "results": [
                {
                    "rnb_id": self.bdg_one.rnb_id,
                    "status": "constructed",
                    "point": {
                        "type": "Point",
                        "coordinates": [0.910481632368284, 44.84916325921506],
                    },
                    "shape": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [0.910400588657524, 44.84928501664322],
                                [0.91029015119156, 44.84910387339187],
                                [0.910569988499674, 44.84904017453093],
                                [0.910669195036661, 44.84922264503825],
                                [0.910400588657524, 44.84928501664322],
                            ]
                        ],
                    },
                    "addresses": [],
                    "ext_ids": [],
                    "is_active": True,
                    "plots": [
                        {"id": "one", "bdg_cover_ratio": 0.529665644404105},
                        {"id": "two", "bdg_cover_ratio": 0.4490196151882506},
                    ],
                },
                {
                    "rnb_id": self.bdg_two.rnb_id,
                    "status": "constructed",
                    "point": {
                        "type": "Point",
                        "coordinates": [0.910251599012782, 44.84955092513704],
                    },
                    "shape": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [0.910139276154524, 44.849463423418655],
                                [0.910327942131403, 44.849432783031574],
                                [0.910382796556888, 44.84963842685542],
                                [0.91014841855926, 44.84964255150933],
                                [0.910139276154524, 44.849463423418655],
                            ]
                        ],
                    },
                    "addresses": [],
                    "ext_ids": [],
                    "is_active": True,
                    "plots": [{"id": "two", "bdg_cover_ratio": 0.0016624281607746448}],
                },
            ],
        }

        # ###############
        # First we check with "withPlots" parameter
        r = self.client.get("/api/alpha/buildings/?withPlots=1")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        self.assertDictEqual(data, expected_w_plots)

        # ###############
        # Then we test the same request without the "withPlots" parameter
        expected_wo_plots = expected_w_plots.copy()
        for bdg in expected_wo_plots["results"]:
            bdg.pop("plots")

        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertDictEqual(data, expected_wo_plots)

        # ###############
        # Finally, we test the request with "withPlots=0"
        r = self.client.get("/api/alpha/buildings/?withPlots=0")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertDictEqual(data, expected_wo_plots)

    def test_no_n_plus_1_query(self):
        Address.objects.create(id="add_1")
        Building.objects.create(rnb_id="A", addresses_id=["add_1"], point="POINT(0 0)")

        Address.objects.create(id="add_2")
        Building.objects.create(rnb_id="B", addresses_id=["add_2"], point="POINT(0 0)")

        def list_buildings():
            self.client.get("/api/alpha/buildings/")

        # 1 for the buildings, 1 for the related addresses, 1 to log the call in rest_framework_tracking_apirequestlog
        self.assertNumQueries(3, list_buildings)

    def test_single_bdg(self):

        expected_w_plots = {
            "rnb_id": self.bdg_one.rnb_id,
            "status": "constructed",
            "point": {
                "type": "Point",
                "coordinates": [0.910481632368284, 44.84916325921506],
            },
            "shape": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [0.910400588657524, 44.84928501664322],
                        [0.91029015119156, 44.84910387339187],
                        [0.910569988499674, 44.84904017453093],
                        [0.910669195036661, 44.84922264503825],
                        [0.910400588657524, 44.84928501664322],
                    ]
                ],
            },
            "addresses": [],
            "ext_ids": [],
            "is_active": True,
            "plots": [
                {"id": "one", "bdg_cover_ratio": 0.529665644404105},
                {"id": "two", "bdg_cover_ratio": 0.4490196151882506},
            ],
        }

        # First we test with "withPlots" parameter = 1
        r = self.client.get(f"/api/alpha/buildings/{self.bdg_one.rnb_id}/?withPlots=1")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertDictEqual(data, expected_w_plots)

        # Then we test without the "withPlots" parameter
        expected_wo_plots = expected_w_plots.copy()
        expected_wo_plots.pop("plots")
        r = self.client.get(f"/api/alpha/buildings/{self.bdg_one.rnb_id}/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertDictEqual(data, expected_wo_plots)

        # Finally, we test with "withPlots=0"
        r = self.client.get(f"/api/alpha/buildings/{self.bdg_one.rnb_id}/?withPlots=0")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertDictEqual(data, expected_wo_plots)
