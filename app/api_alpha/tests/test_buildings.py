import json
from unittest import mock

from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from batid.models import Address
from batid.models import Building
from batid.tests.factories.users import ContributorUserFactory


class BuildingClosestViewTest(APITestCase):
    def test_closest(self):
        user = ContributorUserFactory(username="user")
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
        user = ContributorUserFactory(username="user")

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

        user = ContributorUserFactory(username="user")

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


