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

        print(data)

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

    def test_closest_no_building(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=10"
        )

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"results": [], "next": None, "previous": None})


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

        # comment is mandatory
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
        self.assertEqual(r.status_code, 400)

        data = {
            "status": "constructed",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
        }
        r = self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

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

    def test_update_building(self):
        self.user.groups.add(self.group)
        comment = "maj du batiment"
        data = {
            "status": "notUsable",
            "addresses_cle_interop": [self.adr1.id, self.adr2.id],
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
        self.assertEqual(contribution.status, "fixed")
        self.assertEqual(contribution.text, comment)
        self.assertEqual(contribution.review_user, self.user)

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
