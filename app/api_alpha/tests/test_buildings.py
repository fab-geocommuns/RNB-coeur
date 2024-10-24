import json

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
                            "street_name": None,
                            "street_type": None,
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

        b_1 = Building.objects.create(
            rnb_id="building_1",
            shape=geom,
            point=geom.point_on_surface,
        )

        coords_2 = {
            "coordinates": [
                [
                    [
                        [1.1654705955877262, 46.63423852982024],
                        [1.165454930919401, 46.634105152847496],
                        [1.1656648374661017, 46.63409009413692],
                        [1.1656773692001593, 46.63422131990677],
                        [1.1654705955877262, 46.63423852982024],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom_2 = GEOSGeometry(json.dumps(coords_2), srid=4326)

        b_2 = Building.objects.create(
            rnb_id="building_2",
            shape=geom_2,
            point=geom_2.point_on_surface,
        )

        # request on the building
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=10"
        )
        self.assertEqual(r.status_code, 200)

        data = r.json()
        self.assertEqual(data["rnb_id"], "building_1")
        self.assertEqual(data["distance"], 0.0)

        # request next to the building, 1e-5 difference is about 1m
        lat = 46.63423852982024 + 0.00001
        r = self.client.get(
            f"/api/alpha/buildings/closest/?point={lat},1.0654705955877262&radius=10"
        )
        data = r.json()
        self.assertEqual(data["rnb_id"], "building_1")

        self.assertGreater(data["distance"], 1.0)
        self.assertLess(data["distance"], 2.0)

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

    def test_closest_no_building(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=10"
        )

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"message": "No building found in the area"})


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

        self.assertEqual(self.building.event_type, "delete")
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
