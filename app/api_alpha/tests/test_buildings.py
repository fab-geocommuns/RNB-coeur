import json
from unittest import mock

from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from api_alpha.tests.utils import coordinates_almost_equal
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import User


class BuildingClosestViewTest(APITestCase):
    def test_closest(self):
        user = User.objects.create_user(username="user")
        # It should be first in the results
        closest_bdg = Building.create_new(
            user=user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.56820356, 44.830855],
                                [-0.56843602, 44.830311],
                                [-0.56734383, 44.830072],
                                [-0.56710030, 44.830614],
                                [-0.56820356, 44.830855],
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
            user=user,
            event_origin={"source": "test"},
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
                user=user,
                status="constructed",
                event_origin={"source": "test"},
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
            user=user,
            status="constructed",
            event_origin={"source": "test"},
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
        deactivated_bdg.deactivate(user=user, event_origin={"source": "test"})

        # One demolished building, in radius range
        # It should not appear in the results
        demolished_bdg = Building.create_new(
            user=user,
            status="demolished",
            event_origin={"source": "test"},
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
            user=user,
            status="constructed",
            event_origin={"source": "test"},
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
        self.assertDictEqual(
            data["results"][0]["shape"], json.loads(closest_bdg.shape.geojson)
        )

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

    def test_closest_float_radius(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=30.2"
        )

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"results": [], "next": None, "previous": None})

    def test_closest_0_radius(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=46.63423852982024,1.0654705955877262&radius=0"
        )

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"results": [], "next": None, "previous": None})

    def test_closest_0_lat_lng(self):
        r = self.client.get(
            "/api/alpha/buildings/closest/?point=0.0,1.0654705955877262&radius=10"
        )

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"results": [], "next": None, "previous": None})

        r = self.client.get("/api/alpha/buildings/closest/?point=1.0,0.0&radius=10")

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(r.json(), {"results": [], "next": None, "previous": None})

    def test_closest_no_n_plus_1(self):
        user = User.objects.create_user(username="user")

        Building.create_new(
            user=user,
            event_origin={"source": "test"},
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
            user=user,
            event_origin={"source": "test"},
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

        with CaptureQueriesContext(connection) as queries:
            closest()
            # ignore spatial_ref_sys query because it can be cached and make the number of queries vary
            actual = [q for q in queries if "spatial_ref_sys" not in q["sql"]]
            # would be 4 if N+1 was there
            self.assertEqual(len(actual), 3)


class BuildingAddressViewTest(APITestCase):
    def setUp(self):
        self.cle_interop_ban_1 = "33522_2620_00021"
        self.address_1 = Address.objects.create(id=self.cle_interop_ban_1)
        self.cle_interop_ban_2 = "33522_2620_00022"
        self.address_2 = Address.objects.create(id=self.cle_interop_ban_2)
        self.cle_interop_ban_3 = "33522_2620_00023"
        self.address_3 = Address.objects.create(id=self.cle_interop_ban_3)

        user = User.objects.create_user(username="user")

        self.building_1 = Building.create_new(
            user=user,
            event_origin={"source": "test"},
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
            user=user,
            event_origin={"source": "test"},
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
        def buildings_by_address():
            return self.client.get(
                f"/api/alpha/buildings/address/?cle_interop_ban={self.cle_interop_ban_1}"
            )

        r = buildings_by_address()

        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_1)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score_ban"], None)
        self.assertEqual(
            [r["rnb_id"] for r in data["results"]],
            [self.building_1.rnb_id, self.building_2.rnb_id],
        )
        self.assertNumQueries(3, buildings_by_address)

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


class BuildingMergeTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        UserProfile.objects.create(user=self.user)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.group, created = Group.objects.get_or_create(
            name=RNBContributorPermission.group_name
        )

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

        self.building_1 = Building.objects.create(
            rnb_id="AAAA00000000",
            shape="POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            is_active=True,
            addresses_id=[self.adr1.id],
            ext_ids=[
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )
        self.building_2 = Building.objects.create(
            rnb_id="BBBB00000000",
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
            is_active=True,
            addresses_id=[self.adr2.id],
            ext_ids=[
                {
                    "id": "yyy",
                    "source": "bdtopo",
                    "created_at": "2024-12-07T13:28:58.299402+00:00",
                    "source_version": "2024_01",
                }
            ],
        )

        self.building_3 = Building.objects.create(
            rnb_id="CCCC00000000",
            shape="POINT (10 0)",
            is_active=True,
            addresses_id=[],
        )

        self.building_inactive = Building.objects.create(
            rnb_id="DDDD00000000",
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
            is_active=False,
            addresses_id=[],
        )

    def test_merge_buildings(self):
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
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
        self.assertEqual(res["point"], {"type": "Point", "coordinates": [1.0, 0.5]})
        expectedCoordinates = [
            [
                [0.0, 1.0],
                [2.0, 1.0],
                [2.0, 0.0],
                [0.0, 0.0],
                [0.0, 1.0],
            ]
        ]
        self.assertTrue(
            coordinates_almost_equal.check(
                expectedCoordinates, res["shape"]["coordinates"]
            )
        )
        self.assertEqual(res["shape"]["type"], "Polygon")
        addresses = res["addresses"]
        addresses_ids = [address["id"] for address in addresses]
        addresses_ids.sort()

        expected_addresses = [self.adr1.id, self.adr2.id]
        expected_addresses.sort()

        self.assertListEqual(addresses_ids, expected_addresses)

        self.assertEqual(len(addresses), 2)
        self.assertEqual(
            res["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                },
                {
                    "id": "yyy",
                    "source": "bdtopo",
                    "created_at": "2024-12-07T13:28:58.299402+00:00",
                    "source_version": "2024_01",
                },
            ],
        )

        self.assertTrue(res["is_active"])

        building = Building.objects.get(rnb_id=res["rnb_id"])
        event_origin = building.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_merge_buildings_explicit_addresses(self):
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            # we put a duplicate on purpose
            "addresses_cle_interop": [self.adr1.id, self.adr1.id],
            "comment": "Ces deux bâtiments ne font qu'un, mais une seule adresse est la bonne",
        }

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
        self.assertEqual(res["point"], {"type": "Point", "coordinates": [1.0, 0.5]})

        addresses = res["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr1.id)
        self.assertEqual(len(addresses), 1)

        self.assertEqual(
            res["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                },
                {
                    "id": "yyy",
                    "source": "bdtopo",
                    "created_at": "2024-12-07T13:28:58.299402+00:00",
                    "source_version": "2024_01",
                },
            ],
        )
        self.assertTrue(res["is_active"])

        building = Building.objects.get(rnb_id=res["rnb_id"])
        event_origin = building.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, building.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    def test_merge_buildings_bad_requests(self):
        self.user.groups.add(self.group)

        # not enough rnb_ids to merge
        data = {
            "rnb_ids": [],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # rnb_ids should be a list
        data = {
            "rnb_ids": "coucou",
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # missing status
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "merge_existing_addresses": True,
            "comment": "Ces deux bâtiments ne font qu'un !",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # missing addresses
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "comment": "Ces deux bâtiments ne font qu'un, mais une seule adresse est la bonne",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

        # shapes must be contiguous
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_3.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "Pour fusionner des bâtiments, leurs géométries doivent être des polygones contigus. Veuillez d'abord mettre à jour les géométries des bâtiments",
            r.json()["detail"],
        )

        # one building is not enough
        data = {
            "rnb_ids": [self.building_1.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json(), {"rnb_ids": ["Ensure this field has at least 2 elements."]}
        )

        # cannot merge inactive buildings
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_inactive.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "Cette opération est impossible sur un ID-RNB inactif",
            r.json()["detail"],
        )

        # comment is not mandatory
        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": [self.adr1.id],
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)

    @mock.patch("batid.models.requests.get")
    def test_merge_building_ban_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "addresses_cle_interop": ["33063_9115_00012_bis"],
        }

        self.user.groups.add(self.group)
        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 503)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    def test_merge_buildings_contribution_limit_exceeded(self):
        self.user.groups.add(self.group)

        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        data = {
            "rnb_ids": [self.building_1.rnb_id, self.building_2.rnb_id],
            "status": "constructed",
            "merge_existing_addresses": True,
            "comment": "Fusion de bâtiments",
        }

        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 429)

        # Verify the buildings were not merged
        self.building_1.refresh_from_db()
        self.building_2.refresh_from_db()
        self.assertTrue(self.building_1.is_active)
        self.assertTrue(self.building_2.is_active)
        self.assertNotEqual(self.building_1.event_type, "merge")
        self.assertNotEqual(self.building_2.event_type, "merge")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)


class BuildingSplitTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Robert", last_name="Dylan", username="bob"
        )
        UserProfile.objects.create(user=self.user)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.group, created = Group.objects.get_or_create(
            name=RNBContributorPermission.group_name
        )

        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

        self.building_1 = Building.objects.create(
            rnb_id="AAAA00000000",
            shape="POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            is_active=True,
            addresses_id=[self.adr1.id],
            ext_ids=[
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_split_buildings(self):
        data = {
            "comment": "Ces deux bâtiments ne font qu'un !",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "notUsable",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)
        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)
        res = r.json()

        self.assertEqual(len(res), 2)
        b1 = res[0]

        self.assertEqual(b1["status"], "constructed")
        self.assertEqual(b1["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        self.assertEqual(
            b1["shape"],
            {
                "type": "Polygon",
                "coordinates": [
                    [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
                ],
            },
        )
        addresses = b1["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr1.id)
        self.assertEqual(len(addresses), 1)
        self.assertEqual(
            b1["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )

        self.assertTrue(b1["is_active"])

        b2 = res[1]
        self.assertEqual(b2["status"], "notUsable")
        self.assertEqual(b2["point"], {"type": "Point", "coordinates": [0.5, 0.5]})
        self.assertEqual(
            b1["shape"],
            {
                "type": "Polygon",
                "coordinates": [
                    [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
                ],
            },
        )
        addresses = b2["addresses"]
        self.assertEqual(addresses[0]["id"], self.adr2.id)
        self.assertEqual(len(addresses), 1)
        self.assertEqual(
            b2["ext_ids"],
            [
                {
                    "id": "xxx",
                    "source": "bdnb",
                    "created_at": "2023-12-07T13:28:58.299402+00:00",
                    "source_version": "2023_01",
                }
            ],
        )

        self.assertTrue(b2["is_active"])

        # little check on the parent building
        self.building_1.refresh_from_db()
        self.assertFalse(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, "split")

        event_origin = self.building_1.event_origin
        contribution_id = event_origin.get("contribution_id")

        contribution = Contribution.objects.get(id=contribution_id)

        self.assertEqual(contribution.status, "fixed")
        self.assertFalse(contribution.report, False)
        self.assertEqual(contribution.review_user.id, self.building_1.event_user.id)
        self.assertEqual(contribution.text, data["comment"])

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_split_buildings_missing_info(self):
        self.user.groups.add(self.group)

        # base case: correct
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 201)

        # missing rnb_id
        data = {
            "comment": "Ce sont deux bâtiments",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "notUsable",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)

        # unknown ID-RNB
        data = {
            "comment": "Ce sont deux bâtiments",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "notUsable",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/coucoucoucou/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            r.content, b'{"detail":"No Building matches the given query."}'
        )

        # split in 1 is impossible
        data = {
            "comment": "Ce sont deux bâtiments",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                }
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.content,
            b'{"created_buildings":["Ensure this field has at least 2 elements."]}',
        )

        # missing status in child building
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.content,
            b'{"created_buildings":{"1":{"status":["Ce champ est obligatoire."]}}}',
        )

        # missing address in child building
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.content,
            b'{"created_buildings":{"1":{"addresses_cle_interop":["Ce champ est obligatoire."]}}}',
        )

        # invalid shape
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "coucou",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)
        unicode_content = r.content.decode("utf-8")
        self.assertEqual(
            unicode_content,
            '{"created_buildings":{"1":{"shape":["La forme fournie n\'a pas pu être analysée ou n\'est pas valide"]}}}',
        )

    @mock.patch("batid.models.requests.get")
    def test_merge_building_ban_is_down(self, get_mock):
        get_mock.return_value.status_code = 500
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "Oooops",
        }

        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": ["33063_9115_00012_bis"],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 503)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @mock.patch("batid.models.requests.get")
    def test_merge_building_ban_unknown(self, get_mock):
        get_mock.return_value.status_code = 404
        cle_interop = "33063_9115_00012_bis"
        get_mock.return_value.json.return_value = {
            "details": "unknown",
        }

        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": ["33063_9115_00012_bis"],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        self.user.groups.add(self.group)

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 404)
        get_mock.assert_called_with(
            f"https://plateforme.adresse.data.gouv.fr/lookup/{cle_interop}"
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_split_buildings_contribution_limit_exceeded(self):
        self.user.groups.add(self.group)

        # Set user to have reached their contribution limit
        self.user.profile.total_contributions = 500
        self.user.profile.max_allowed_contributions = 500
        self.user.profile.save()

        data = {
            "comment": "Division du bâtiment",
            "created_buildings": [
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr1.id],
                },
                {
                    "status": "constructed",
                    "shape": "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "addresses_cle_interop": [self.adr2.id],
                },
            ],
        }

        r = self.client.post(
            f"/api/alpha/buildings/{self.building_1.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 429)

        # Verify the building was not split
        self.building_1.refresh_from_db()
        self.assertTrue(self.building_1.is_active)
        self.assertNotEqual(self.building_1.event_type, "split")

        # Verify user contribution count did not increase
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.total_contributions, 500)
