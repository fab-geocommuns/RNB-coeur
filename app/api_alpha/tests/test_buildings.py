import json
from unittest import mock

from batid.models import Address, Building
from batid.tests.factories.users import ContributorUserFactory
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase


class BuildingClosestViewTest(APITestCase):
    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_closest(self):

        user = ContributorUserFactory(username="user")

        # It should be first in the results
        closest_bdg = Building.create_new(
            user=user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_cle_interop=[],
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

        closest_bdg.validated_by = [user.id]
        closest_bdg.save()

        # It should appear second in the results
        further_bdg = Building.create_new(
            user=user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_cle_interop=[],
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
                addresses_cle_interop=[],
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
            addresses_cle_interop=[],
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
            addresses_cle_interop=[],
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
            addresses_cle_interop=[],
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
        self.assertListEqual(
            data["results"][0]["validated_by"],
            [
                {
                    "id": user.id,
                    "username": user.username,
                    "organization_name": None,
                    "organization_short_name": None,
                }
            ],
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

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_closest_no_n_plus_1(self):
        user = ContributorUserFactory(username="user")

        Building.create_new(
            user=user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_cle_interop=[],
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
            addresses_cle_interop=[],
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
            # would be 5 if N+1 was there
            self.assertEqual(len(actual), 4)


class BuildingAddressViewTest(APITestCase):
    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def setUp(self):
        self.cle_interop_ban_1 = "33522_2620_00021"
        self.address_1 = Address.objects.create(cle_interop=self.cle_interop_ban_1)
        self.cle_interop_ban_2 = "33522_2620_00022"
        self.address_2 = Address.objects.create(cle_interop=self.cle_interop_ban_2)
        self.cle_interop_ban_3 = "33522_2620_00023"
        self.address_3 = Address.objects.create(cle_interop=self.cle_interop_ban_3)

        self.user = ContributorUserFactory(username="user")

        self.building_1 = Building.create_new(
            user=self.user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_cle_interop=[self.cle_interop_ban_1, self.cle_interop_ban_2],
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

        self.building_1.validated_by = [self.user.id]
        self.building_1.save()

        self.building_2 = Building.create_new(
            user=self.user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_cle_interop=[self.cle_interop_ban_1],
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

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_allowed_parameters(self):
        r = self.client.get("/api/alpha/buildings/address/")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/alpha/buildings/address/?min_score=0.7")
        self.assertEqual(r.status_code, 400)

        r = self.client.get(
            f"/api/alpha/buildings/address/?min_score=0.7&cle_interop_ban={self.cle_interop_ban_1}"
        )
        self.assertEqual(r.status_code, 400)

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
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
        self.assertNumQueries(5, buildings_by_address)

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
        self.assertListEqual(
            data["results"][0]["validated_by"],
            [
                {
                    "id": self.user.id,
                    "username": self.user.username,
                    "organization_name": None,
                    "organization_short_name": None,
                }
            ],
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

    @mock.patch("batid.services.geocoders.requests.get")
    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
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

    @mock.patch("batid.services.geocoders.requests.get")
    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
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

    @mock.patch("batid.services.geocoders.requests.get")
    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_address_ban_5XX(self, get_mock):
        get_mock.return_value.status_code = 500
        q = "1 route de Toulouse"
        get_mock.return_value.json.return_value = {"status": "error"}

        r = self.client.get(f"/api/alpha/buildings/address/?q={q}")
        self.assertEqual(r.status_code, 503)

    URL = "/api/alpha/buildings/address/"
    BAN_ID = "fd9736e8-9970-4127-84eb-f2886043c122"
    OTHER_BAN_ID = "207eecbf-689c-4d90-a755-cb193ad537cb"

    def _set_ban_id(self, address, ban_id):
        Address.objects.filter(pk=address.pk).update(ban_id=ban_id)

    def _building_at(self, rnb_id, cle_interops, status="constructed", is_active=True):
        """Create a building linked to already existing addresses."""
        point = GEOSGeometry("POINT(2.35 48.85)", srid=4326)
        return Building.objects.create(
            rnb_id=rnb_id,
            shape=point,
            point=point,
            status=status,
            is_active=is_active,
            addresses_internal_id=list(
                Address.objects.filter(cle_interop__in=cle_interops).values_list(
                    "internal_id", flat=True
                )
            ),
        )

    def _geocode(self, get_mock, cle_interop, ban_id=None, score=0.9):
        """Make the mocked geocoder answer one housenumber, then call the endpoint."""
        properties = {"id": cle_interop, "type": "housenumber", "score": score}
        if ban_id is not None:
            properties["banId"] = ban_id
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {
            "features": [{"type": "Feature", "properties": properties}]
        }
        return self.client.get(self.URL, {"q": "8 Boulevard du Port"})

    def _rnb_ids(self, response):
        return [b["rnb_id"] for b in response.json()["results"]]

    def test_search_params_are_exclusive(self):
        """
        Input: no search parameter, or several among q, cle_interop_ban and ban_id.
        Expected: 400 for each combination.
        """
        key = self.cle_interop_ban_1
        for params in (
            {},
            {"q": "a", "ban_id": self.BAN_ID},
            {"cle_interop_ban": key, "ban_id": self.BAN_ID},
            {"q": "a", "cle_interop_ban": key},
            {"q": "a", "cle_interop_ban": key, "ban_id": self.BAN_ID},
        ):
            with self.subTest(params=params):
                r = self.client.get(self.URL, params)
                self.assertEqual(r.status_code, 400, r.content)
                self.assertIn("non_field_errors", r.json())

    def test_ban_id_with_min_score_is_refused(self):
        """
        Input: ban_id with min_score, including the falsy value 0.
        Expected: 400.
        """
        for min_score in ("0", "0.5", "1"):
            with self.subTest(min_score=min_score):
                r = self.client.get(
                    self.URL, {"ban_id": self.BAN_ID, "min_score": min_score}
                )
                self.assertEqual(r.status_code, 400, r.content)

    def test_invalid_ban_id_is_refused(self):
        """
        Input: ban_id values which are not UUIDs.
        Expected: 400 on the ban_id field, never a 500.
        """
        for ban_id in ("nope", self.BAN_ID[:-1], "\x00"):
            with self.subTest(ban_id=ban_id):
                r = self.client.get(self.URL, {"ban_id": ban_id})
                self.assertEqual(r.status_code, 400, r.content)
                self.assertIn("ban_id", r.json())

    def test_by_ban_id(self):
        """
        Input: ban_id of an address linked to 2 buildings, in lower then upper case.
        Expected: the 2 buildings, ban_id returned as a lowercase string,
        cle_interop_ban and score_ban null.
        """
        self._set_ban_id(self.address_1, self.BAN_ID)

        for value in (self.BAN_ID, self.BAN_ID.upper()):
            with self.subTest(value=value):
                r = self.client.get(self.URL, {"ban_id": value})
                self.assertEqual(r.status_code, 200)
                data = r.json()
                self.assertEqual(data["ban_id"], self.BAN_ID)
                self.assertIsNone(data["cle_interop_ban"])
                self.assertIsNone(data["score_ban"])
                self.assertEqual(data["status"], "ok")
                self.assertEqual(
                    self._rnb_ids(r),
                    [self.building_1.rnb_id, self.building_2.rnb_id],
                )

    def test_by_unknown_ban_id(self):
        """
        Input: valid UUID held by no address.
        Expected: 200, status ok, no building, the ban_id echoed.
        """
        r = self.client.get(self.URL, {"ban_id": self.BAN_ID})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["ban_id"], self.BAN_ID)
        self.assertEqual(data["results"], [])

    def test_by_ban_id_ignores_inactive_buildings_only(self):
        """
        Input: ban_id of an address linked to an inactive and a demolished building.
        Expected: only the demolished one: the status is not filtered here.
        """
        self._set_ban_id(self.address_3, self.BAN_ID)
        self._building_at("INACTIVEINAC", [self.cle_interop_ban_3], is_active=False)
        demolished = self._building_at(
            "DEMOLISHEDDE", [self.cle_interop_ban_3], status="demolished"
        )

        r = self.client.get(self.URL, {"ban_id": self.BAN_ID})
        self.assertEqual(self._rnb_ids(r), [demolished.rnb_id])

    def test_cle_interop_is_case_insensitive_without_duplicate(self):
        """
        Input: cle_interop_ban in another case; a building linked to both spellings.
        Expected: the building comes out once, the received value is returned and
        ban_id is null.
        """
        Address.objects.create(cle_interop="2a004_abcd_00001")
        Address.objects.create(cle_interop="2A004_ABCD_00001")
        both = self._building_at(
            "BOTHBOTHBOTH", ["2a004_abcd_00001", "2A004_ABCD_00001"]
        )

        r = self.client.get(self.URL, {"cle_interop_ban": "2A004_aBcD_00001"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(self._rnb_ids(r), [both.rnb_id])
        self.assertEqual(data["cle_interop_ban"], "2A004_aBcD_00001")
        self.assertIsNone(data["ban_id"])

    def test_cle_interop_still_matches_address_with_ban_id(self):
        """
        Input: cle_interop_ban param on an address holding a BAN ID.
        Expected: the buildings are found (the NULL restriction only applies to q)
        and ban_id is null since the filter used the key.
        """
        self._set_ban_id(self.address_2, self.BAN_ID)

        r = self.client.get(self.URL, {"cle_interop_ban": self.cle_interop_ban_2})
        self.assertEqual(self._rnb_ids(r), [self.building_1.rnb_id])
        self.assertIsNone(r.json()["ban_id"])

    @mock.patch("batid.services.geocoders.requests.get")
    def test_q_filters_on_ban_id_when_held_locally(self, get_mock):
        """
        Input: geocoder returns a key and a banId; the banId is held by a local
        address having a different key.
        Expected: filter on ban_id (buildings of that address), ban_id returned,
        cle_interop_ban keeps the geocoded value.
        """
        self._set_ban_id(self.address_2, self.BAN_ID)

        r = self._geocode(get_mock, self.cle_interop_ban_1, ban_id=self.BAN_ID)

        data = r.json()
        self.assertEqual(self._rnb_ids(r), [self.building_1.rnb_id])
        self.assertEqual(data["ban_id"], self.BAN_ID)
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_1)
        self.assertEqual(data["status"], "ok")

    @mock.patch("batid.services.geocoders.requests.get")
    def test_q_falls_back_on_key_when_ban_id_unknown(self, get_mock):
        """
        Input: geocoded banId held by no local address; the local address with the
        geocoded key has a NULL ban_id.
        Expected: filter on the key, and ban_id null since it was not used.
        """
        r = self._geocode(get_mock, self.cle_interop_ban_1, ban_id=self.BAN_ID)

        data = r.json()
        self.assertEqual(
            self._rnb_ids(r), [self.building_1.rnb_id, self.building_2.rnb_id]
        )
        self.assertIsNone(data["ban_id"])
        self.assertEqual(data["cle_interop_ban"], self.cle_interop_ban_1)

    @mock.patch("batid.services.geocoders.requests.get")
    def test_q_does_not_match_reassigned_key(self, get_mock):
        """
        Input: geocoded banId held by no local address; the local address with the
        geocoded key holds another BAN ID (the key has been reassigned).
        Expected: status ok, no building, ban_id null.
        """
        self._set_ban_id(self.address_1, self.OTHER_BAN_ID)

        r = self._geocode(get_mock, self.cle_interop_ban_1, ban_id=self.BAN_ID)

        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["results"], [])
        self.assertIsNone(data["ban_id"])

    @mock.patch("batid.services.geocoders.requests.get")
    def test_q_without_ban_id_matches_key_whatever_local_ban_id(self, get_mock):
        """
        Input: geocoder returns no banId, first for a local address with a NULL
        ban_id, then for a local address holding a BAN ID.
        Expected: the building is found in both cases, with ban_id null in the
        response since the filter used the key.
        """
        r = self._geocode(get_mock, self.cle_interop_ban_2)
        self.assertEqual(self._rnb_ids(r), [self.building_1.rnb_id])
        self.assertIsNone(r.json()["ban_id"])

        self._set_ban_id(self.address_2, self.BAN_ID)
        r = self._geocode(get_mock, self.cle_interop_ban_2)
        self.assertEqual(self._rnb_ids(r), [self.building_1.rnb_id])
        self.assertIsNone(r.json()["ban_id"])

    @mock.patch("batid.services.geocoders.requests.get")
    def test_q_with_malformed_ban_id_falls_back_on_key(self, get_mock):
        """
        Input: geocoder returns a banId which is not a UUID, first for a local
        address with a NULL ban_id, then for a local address holding a BAN ID.
        Expected: no error, the building is found in both cases, ban_id null.
        """
        r = self._geocode(get_mock, self.cle_interop_ban_2, ban_id="not-a-uuid")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._rnb_ids(r), [self.building_1.rnb_id])
        self.assertIsNone(r.json()["ban_id"])

        self._set_ban_id(self.address_2, self.BAN_ID)
        r = self._geocode(get_mock, self.cle_interop_ban_2, ban_id="not-a-uuid")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._rnb_ids(r), [self.building_1.rnb_id])
        self.assertIsNone(r.json()["ban_id"])

    @mock.patch("batid.services.geocoders.requests.get")
    def test_q_fallback_ignores_case_and_skips_reassigned_spelling(self, get_mock):
        """
        Input: geocoded key in lowercase; local addresses abc (NULL ban_id) and ABC
        (another BAN ID), each with its building.
        Expected: only the building of the NULL address.
        """
        Address.objects.create(cle_interop="2a004_abcd_00001")
        Address.objects.create(cle_interop="2A004_ABCD_00001", ban_id=self.OTHER_BAN_ID)
        lower = self._building_at("LOWERLOWERLO", ["2a004_abcd_00001"])
        self._building_at("UPPERUPPERUP", ["2A004_ABCD_00001"])

        r = self._geocode(get_mock, "2a004_abcd_00001", ban_id=self.BAN_ID)

        self.assertEqual(self._rnb_ids(r), [lower.rnb_id])

    @mock.patch("batid.services.geocoders.requests.get")
    def test_ban_id_is_null_on_geocoding_failures(self, get_mock):
        """
        Input: geocoding with no result, then with a score below min_score while a
        local address holds the geocoded banId.
        Expected: the matching status, no results and ban_id null in both cases.
        """
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {"features": []}
        data = self.client.get(self.URL, {"q": "lkjlkj"}).json()
        self.assertEqual(data["status"], "geocoding_no_result")
        self.assertIsNone(data["ban_id"])
        self.assertIsNone(data["results"])

        self._set_ban_id(self.address_1, self.BAN_ID)
        data = self._geocode(
            get_mock, self.cle_interop_ban_1, ban_id=self.BAN_ID, score=0.5
        ).json()
        self.assertEqual(data["status"], "geocoding_score_is_too_low")
        self.assertIsNone(data["ban_id"])
        self.assertIsNone(data["results"])

    def test_pagination_keeps_ban_id(self):
        """
        Input: ban_id of an address with 2 buildings, limit=1.
        Expected: two pages of one building each, in id order, with ban_id on both.
        """
        self._set_ban_id(self.address_1, self.BAN_ID)

        first = self.client.get(self.URL, {"ban_id": self.BAN_ID, "limit": 1}).json()
        self.assertEqual(
            [b["rnb_id"] for b in first["results"]], [self.building_1.rnb_id]
        )
        second = self.client.get(first["next"]).json()
        self.assertEqual(
            [b["rnb_id"] for b in second["results"]], [self.building_2.rnb_id]
        )
        self.assertEqual(second["ban_id"], self.BAN_ID)
        self.assertIsNone(second["next"])
