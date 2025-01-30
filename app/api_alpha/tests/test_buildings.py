import json
from unittest import mock

from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import Organization
from batid.models import Plot
from batid.models import User
from batid.tests.helpers import create_bdg
from batid.tests.helpers import create_grenoble


class BuildingsEndpointsTest(APITestCase):
    maxDiff = None

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


class BuildingClosestViewTest(APITestCase):
    def test_closest(self):

        # It should be first in the results
        closest_bdg = Building.create_new(
            user=None,
            event_origin="test",
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5682035663317322, 44.83085542749811],
                                [-0.56843602659049, 44.83031112933102],
                                [-0.5673438323587163, 44.83007299726728],
                                [-0.5671003025640005, 44.83061468086615],
                                [-0.5682035663317322, 44.83085542749811],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        # It should appear second in the results
        further_bdg = Building.create_new(
            user=None,
            event_origin="test",
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5683373823683553, 44.83085611997467],
                                [-0.5685621443934679, 44.83091091343829],
                                [-0.5688395850185373, 44.83040282659957],
                                [-0.568530537234011, 44.83032561693295],
                                [-0.5683373823683553, 44.83085611997467],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        # We create many buildings to test pagination
        # They are in range and should appear in the results
        for i in range(20):
            Building.create_new(
                user=None,
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

        # One deactivated building, in radius range
        # It should not appear in the results
        deactivated_bdg = Building.create_new(
            user=None,
            status="constructed",
            event_origin="test",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.568078311510078, 44.83092439844569],
                                [-0.5678527488539089, 44.831017565877204],
                                [-0.5680411308524356, 44.83105623910677],
                                [-0.568078311510078, 44.83092439844569],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )
        deactivated_bdg.deactivate(user=None, event_origin="test")

        # One demolished building, in radius range
        # It should not appear in the results
        demolished_bdg = Building.create_new(
            user=None,
            status="demolished",
            event_origin="test",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5679742056692021, 44.83088396724915],
                                [-0.5677833449604464, 44.830852325423905],
                                [-0.5678056533552933, 44.830931429955456],
                                [-0.5679742056692021, 44.83088396724915],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        # One building way too far
        # It should not appear in the results
        very_far_bdg = Building.create_new(
            user=None,
            status="constructed",
            event_origin="test",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [2.3389792007339736, 48.84729730300006],
                                [2.3389049893044103, 48.84727559802761],
                                [2.3388839169221853, 48.84722917347267],
                                [2.338912318827653, 48.84718274887467],
                                [2.338959044543145, 48.847165867191706],
                                [2.3390250102591494, 48.84717069053036],
                                [2.339064406450433, 48.84719179263064],
                                [2.3390891435943217, 48.84722615888933],
                                [2.3390772331180756, 48.84726534845461],
                                [2.3390479150212116, 48.847286450515014],
                                [2.339014932163707, 48.847299714662796],
                                [2.3389792007339736, 48.84729730300006],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        r = self.client.get(
            "/api/alpha/buildings/closest/?point=44.83045932150495,-0.5675637291200246&radius=1000"
        )

        self.assertEqual(r.status_code, 200)

        data = r.json()

        # Check that the closest building is first
        self.assertEqual(data["results"][0]["rnb_id"], closest_bdg.rnb_id)

        # Check that the further building is second
        self.assertEqual(data["results"][1]["rnb_id"], further_bdg.rnb_id)

        # Check there is a "next" url
        self.assertIsNotNone(data["next"])

        # Check there is no "previous" url
        self.assertIsNone(data["previous"])

        # Get all RNB IDs (in both pages of result)
        second_page_data = self.client.get(data["next"]).json()

        first_page = [building["rnb_id"] for building in data["results"]]
        second_page = [building["rnb_id"] for building in second_page_data["results"]]

        all_rnb_ids = first_page + second_page

        self.assertEqual(len(all_rnb_ids), 22)

        # Check that the deactivated building is not in the results
        self.assertNotIn(deactivated_bdg.rnb_id, all_rnb_ids)

        # Check that the demolished building is not in the results
        self.assertNotIn(demolished_bdg.rnb_id, all_rnb_ids)

        # Check the very far building is not in the results
        self.assertNotIn(very_far_bdg.rnb_id, all_rnb_ids)

    def test_closest_invalid_query_params(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262"
        )
        self.assertEqual(r.status_code, 400)

        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=foo"
        )
        self.assertEqual(r.status_code, 400)

        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=-10"
        )
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/closest/?radius=10")
        self.assertEqual(r.status_code, 400)

        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=2000"
        )
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/closest/?point=999,999&radius=-10")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/closest/?point=NaN,1.0&radius=10")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/closest/?point=1.0,NaN&radius=10")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/closest/?point=1.0,200&radius=10")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/closest/?point=-100,0&radius=10")
        self.assertEqual(r.status_code, 400)

    def test_closest_no_building(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=10"
        )

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"results": [], "next": None, "previous": None})

    def test_closes_no_n_plus_1(self):
        Building.create_new(
            user=None,
            event_origin="test",
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5682035663317322, 44.83085542749811],
                                [-0.56843602659049, 44.83031112933102],
                                [-0.5673438323587163, 44.83007299726728],
                                [-0.5671003025640005, 44.83061468086615],
                                [-0.5682035663317322, 44.83085542749811],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )
        Building.create_new(
            user=None,
            event_origin="test",
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5682035663317322, 44.83085542749811],
                                [-0.56843602659049, 44.83031112933102],
                                [-0.5673438323587163, 44.83007299726728],
                                [-0.5671003025640005, 44.83061468086615],
                                [-0.5682035663317322, 44.83085542749811],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        def closest():
            self.client.get(
                "/api/alpha/buildings/closest/?point=44.83045932150495,-0.5675637291200246&radius=1000"
            )

        # would be 5 if N+1 was there
        self.assertNumQueries(4, closest)


class BuildingAddressViewTest(APITestCase):
    def setUp(self):
        self.cle_interop_ban_1 = "33522_2620_00021"
        self.address_1 = Address.objects.create(id=self.cle_interop_ban_1)
        self.cle_interop_ban_2 = "33522_2620_00022"
        self.address_2 = Address.objects.create(id=self.cle_interop_ban_2)
        self.cle_interop_ban_3 = "33522_2620_00023"
        self.address_3 = Address.objects.create(id=self.cle_interop_ban_3)

        self.building_1 = Building.create_new(
            user=None,
            event_origin="test",
            status="constructed",
            addresses_id=[self.cle_interop_ban_1, self.cle_interop_ban_2],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5682035663317322, 44.83085542749811],
                                [-0.56843602659049, 44.83031112933102],
                                [-0.5673438323587163, 44.83007299726728],
                                [-0.5671003025640005, 44.83061468086615],
                                [-0.5682035663317322, 44.83085542749811],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        self.building_2 = Building.create_new(
            user=None,
            event_origin="test",
            status="constructed",
            addresses_id=[self.cle_interop_ban_1],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5682035663317322, 44.83085542749811],
                                [-0.56843602659049, 44.83031112933102],
                                [-0.5673438323587163, 44.83007299726728],
                                [-0.5671003025640005, 44.83061468086615],
                                [-0.5682035663317322, 44.83085542749811],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

    def test_allowed_parameters(self):
        r = self.client.get("/api/alpha/buildings/address/")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/address/?min_score=0.7")
        self.assertEqual(r.status_code, 400)

        r = self.client.get(
            f"/api/alpha/buildings/address/?min_score=0.7&cle_interop_ban={self.cle_interop_ban_1}"
        )
        self.assertEqual(r.status_code, 400)

    def test_by_cle_interop(self):
        # 2 buildings
        r = self.client.get(
            f"/api/alpha/buildings/address/?cle_interop_ban={self.cle_interop_ban_1}"
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_1)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score_ban"], None)
        self.assertEqual(
            [r["rnb_id"] for r in data["results"]],
            [self.building_1.rnb_id, self.building_2.rnb_id],
        )

        # 1 building
        r = self.client.get(
            f"/api/alpha/buildings/address/?cle_interop_ban={self.cle_interop_ban_2}"
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_2)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score_ban"], None)
        self.assertEqual(
            [r["rnb_id"] for r in data["results"]], [self.building_1.rnb_id]
        )

        # 0 building
        r = self.client.get(
            f"/api/alpha/buildings/address/?cle_interop_ban={self.cle_interop_ban_3}"
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_3)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score_ban"], None)
        self.assertEqual(data["results"], [])

        # cle_interop_ban unknown
        r = self.client.get(f"/api/alpha/buildings/address/?cle_interop_ban=coucou")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], "coucou")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score_ban"], None)
        self.assertEqual(data["results"], [])

    @mock.patch("api_alpha.views.requests.get")
    def test_by_address(self, get_mock):
        get_mock.return_value.status_code = 200
        q = "8 Boulevard du Port 95000 Cergy"

        get_mock.return_value.json.return_value = {
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "label": f"{q}",
                        "score": 0.85,
                        "id": f"{self.cle_interop_ban_1}",
                        "type": "housenumber",
                    },
                }
            ]
        }

        # 2 buildings
        r = self.client.get(f"/api/alpha/buildings/address/?q={q}")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_1)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score_ban"], 0.85)
        self.assertEqual(
            [r["rnb_id"] for r in data["results"]],
            [self.building_1.rnb_id, self.building_2.rnb_id],
        )

        # custom and high min_score => no results
        r = self.client.get(f"/api/alpha/buildings/address/?q={q}&min_score=0.9")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_1)
        self.assertEqual(data["status"], "geocoding_score_is_too_low")
        self.assertEqual(data["score_ban"], 0.85)
        self.assertEqual(data["results"], None)

    @mock.patch("api_alpha.views.requests.get")
    def test_address_not_found_on_ban(self, get_mock):
        get_mock.return_value.status_code = 200
        q = "lkjlkjlkjlkj"
        get_mock.return_value.json.return_value = {"features": []}

        # no building found
        r = self.client.get(f"/api/alpha/buildings/address/?q={q}")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], None)
        self.assertEqual(data["status"], "geocoding_no_result")
        self.assertEqual(data["score_ban"], None)
        self.assertEqual(data["results"], None)

    @mock.patch("api_alpha.views.requests.get")
    def test_address_ban_5XX(self, get_mock):
        get_mock.return_value.status_code = 500
        q = "1 route de Toulouse"
        get_mock.return_value.json.return_value = {"status": "error"}

        r = self.client.get(f"/api/alpha/buildings/address/?q={q}")
        self.assertEqual(r.status_code, 503)


class BuildingPlotViewTest(APITestCase):
    def test_buildings_on_plot(self):
        Plot.objects.create(
            id="plot_1", shape="MULTIPOLYGON(((0 0, 0 1, 1 1, 1 0, 0 0)))"
        )
        Plot.objects.create(
            id="plot_2", shape="MULTIPOLYGON(((1 1, 1 2, 2 2, 2 1, 1 1)))"
        )

        # inside plot 1
        building_1 = Building.objects.create(
            rnb_id="building_1",
            shape="POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
            status="demolished",
        )
        building_1.point = building_1.shape.point_on_surface
        building_1.save()
        # inside plot 1 but inactive
        building_2 = Building.objects.create(
            rnb_id="building_2",
            shape="POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
            is_active=False,
        )
        building_2.point = building_2.shape.point_on_surface
        building_2.save()

        # # partially on plot_1 and plot_2
        building_3 = Building.objects.create(
            rnb_id="building_3",
            shape="POLYGON((0.5 0.5, 0.5 1.5, 1.5 1.5, 1.5 0.5, 0.5 0.5))",
            is_active=True,
        )
        building_3.point = building_3.shape.point_on_surface
        building_3.save()

        # # plot_1 and plot_2 are completely inside building_4 and _5
        building_4 = Building.objects.create(
            rnb_id="building_4", shape="POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))"
        )
        building_4.point = building_4.shape.point_on_surface
        building_4.save()
        # (but this one is inactive)
        building_5 = Building.objects.create(
            rnb_id="building_5",
            shape="POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
            is_active=False,
        )
        building_5.point = building_5.shape.point_on_surface
        building_5.save()

        # building_6 is a point
        building_6 = Building.objects.create(
            rnb_id="building_6", shape="POINT(0.5 0.5)", point="POINT(0.5 0.5)"
        )

        r = self.client.get("/api/alpha/buildings/plot/plot_1/")
        self.assertEqual(r.status_code, 200)
        data = r.json()

        [r1, r2, r3, r4] = data["results"]
        self.assertEqual(r1["rnb_id"], building_1.rnb_id)
        # building_1 is 100% included in the plot
        self.assertEqual(r1["bdg_cover_ratio"], 1.0)

        self.assertEqual(r2["rnb_id"], building_6.rnb_id)
        # building_6 is 100% included in the plot, it's a point!
        self.assertEqual(r1["bdg_cover_ratio"], 1.0)

        self.assertEqual(r3["rnb_id"], building_3.rnb_id)
        # building_3 is 25% included in the plot
        self.assertEqual(r3["bdg_cover_ratio"], 0.25)

        self.assertEqual(r4["rnb_id"], building_4.rnb_id)
        # building_4 is 25% included in the plot
        self.assertEqual(r4["bdg_cover_ratio"], 0.25)

        r = self.client.get("/api/alpha/buildings/plot/plot_2/")
        self.assertEqual(r.status_code, 200)
        data = r.json()

        [r1, r2] = data["results"]
        self.assertEqual(r1["rnb_id"], building_3.rnb_id)
        # building_1 is 100% included in the plot
        self.assertEqual(r1["bdg_cover_ratio"], 0.25)

        self.assertEqual(r2["rnb_id"], building_4.rnb_id)
        # building_3 is 25% included in the plot
        self.assertEqual(r2["bdg_cover_ratio"], 0.25)

    def test_buildings_on_unknown_plot(self):
        r = self.client.get("/api/alpha/buildings/plot/coucou/")
        self.assertEqual(r.status_code, 404)
        res = r.json()
        self.assertEqual(res["detail"], "Plot unknown")


class BuildingPatchTest(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )

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

        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

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

        # not a building
        data = {"is_active": False, "comment": "not a building"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

        # update status ok
        data = {"status": "demolished", "comment": "démoli"}
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 204)

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
            user=None,
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
        self.assertEqual(self.building.addresses_id, [self.adr1.id, self.adr2.id])
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


class BuildingPostTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.group, created = Group.objects.get_or_create(
            name=RNBContributorPermission.group_name
        )

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

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

        self.assertEqual(r.status_code, 403)

        self.user.groups.add(self.group)

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

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_create_building_missing_status(self):
        data = {
            "addresses_cle_interop": ["cle_interop_1"],
            "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "comment": "nouveau bâtiment",
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

    @mock.patch("batid.models.requests.get")
    def test_create_building_ban_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        self.user.groups.add(self.group)
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


class BuildingMergeTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.group, created = Group.objects.get_or_create(
            name=RNBContributorPermission.group_name
        )

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

    def test_merge_buildings(self):
        building_1 = Building.objects.create(
            rnb_id="AAAA00000000",
            shape="POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            is_active=True,
            addresses_id=[self.adr1.id],
        )
        building_2 = Building.objects.create(
            rnb_id="BBBB00000000",
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
            is_active=True,
            addresses_id=[self.adr2.id],
        )

        data = {
            "rnb_ids": [building_1.rnb_id, building_2.rnb_id],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)
        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)
        res = r.json()

        self.assertTrue(res["rnb_id"])
        self.assertEqual(res["status"], "constructed")
        # self.assertEqual(res["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        # self.assertEqual(
        #     res["shape"],
        #     {
        #         "type": "Polygon",
        #         "coordinates": [
        #             [[0.0, 0.0], [0.0, 2.0], [2.0, 2.0], [2.0, 0.0], [0.0, 0.0]]
        #         ],
        #     },
        # )
        addresses = res["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr1.id)
        self.assertEqual(addresses[1]["id"], self.adr2.id)
        self.assertEqual(len(addresses), 2)
        # to do
        self.assertEqual(res["ext_ids"], [])
        self.assertTrue(res["is_active"])

        building = Building.objects.get(rnb_id=res["rnb_id"])
        event_origin = building.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])


class BuildingsWithPlots(APITestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bdg_one = None
        self.bdg_two = None

    def setUp(self):
        # The two plots are side by side

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
            user=None,
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
            user=None,
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
