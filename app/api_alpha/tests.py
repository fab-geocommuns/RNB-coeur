import json

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase
from batid.models import Building, ADS, BuildingADS


class EndpointsTest(APITestCase):
    def setUp(self):
        self.__insert_data()

    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

    def test_ads_root(self):
        r = self.client.get("/api/alpha/ads/")
        self.assertEqual(r.status_code, 200)

    def test_ads_search_since(self):
        r = self.client.get("/api/alpha/ads/?since=2024-12-01")
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        expected = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "issue_number": "ADS-TEST-FUTURE",
                    "issue_date": "2025-01-02",
                    "buildings_operations": [],
                }
            ],
        }
        self.assertDictEqual(r_data, expected)

    def test_ads_search_q(self):
        r = self.client.get("/api/alpha/ads/?q=future")
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        expected = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "issue_number": "ADS-TEST-FUTURE",
                    "issue_date": "2025-01-02",
                    "buildings_operations": [],
                }
            ],
        }
        self.assertDictEqual(r_data, expected)

    def test_read_one_ads(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST/")
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        expected = {
            "issue_number": "ADS-TEST",
            "issue_date": "2019-01-01",
            "buildings_operations": [
                {"operation": "build", "building": {"rnb_id": "BDG-RNB-ID"}}
            ],
        }
        self.assertDictEqual(r_data, expected)

    def test_create_simple_ads(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-01",
        }

        r = self.client.post("/api/alpha/ads/", data=data)
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        expected = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-01",
            "buildings_operations": [],
        }
        self.assertDictEqual(r_data, expected)

    def test_create_ads(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDG-RNB-ID"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        expected = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-RNB-ID",
                    },
                }
            ],
        }
        # Assert that the response is correct
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 200)

        # Assert that the data is correctly saved
        r = self.client.get("/api/alpha/ads/ADS-TEST-2/")
        r_data = r.json()
        self.assertDictEqual(r_data, expected)

    def test_ads_create_with_new_bdg(self):
        data = {
            "issue_number": "ADS-TEST-NEW-BDG",
            "issue_date": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "lat": 44.7802149854455,
                        "lng": -0.4617233264741004,
                    },
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()
        new_rnb_id = r_data["buildings_operations"][0]["building"]["rnb_id"]

        expected = {
            "issue_number": "ADS-TEST-NEW-BDG",
            "issue_date": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                    },
                }
            ],
        }
        # Assert that the response is correct
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 200)

        # Assert that the data is correctly saved
        r = self.client.get("/api/alpha/ads/ADS-TEST-NEW-BDG/")
        r_data = r.json()
        self.assertDictEqual(r_data, expected)

    def test_ads_update_simple(self):
        data = {"issue_number": "ADS-TEST-UPDATE", "issue_date": "2025-01-02"}

        r = self.client.put("/api/alpha/ads/ADS-TEST-UPDATE/", data=data)
        self.assertEqual(r.status_code, 200)

        expected = {
            "issue_number": "ADS-TEST-UPDATE",
            "issue_date": "2025-01-02",
            "buildings_operations": [],
        }
        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE/")
        r_data = r.json()
        print(r_data)
        self.assertDictEqual(r_data, expected)

    def test_ads_update_with_new_bdg(self):
        data = {
            "issue_number": "ADS-TEST-UPDATE-BDG",
            "issue_date": "2025-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "lat": 44.7802149854455,
                        "lng": -0.4617233264741004,
                    },
                }
            ],
        }

        r = self.client.put("/api/alpha/ads/ADS-TEST-UPDATE-BDG/", data=data)
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE-BDG/")
        r_data = r.json()
        print(r_data)

    def test_ads_same_bdg_twice(self):
        data = {
            "issue_number": "ADS-TEST-BDG-TWICE",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDG-RNB-ID"},
                },
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDG-RNB-ID"},
                },
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {
            "buildings_operations": "A building can only be present once in an ADS."
        }

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_issue_number(self):
        data = {"issue_number": "ADS-TEST", "issue_date": "2019-01-02"}
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {"issue_number": "This issue number already exists"}

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_issue_date(self):
        data = {"issue_number": "ADS-TEST-DATE", "issue_date": "2019-13-01"}
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {
            "issue_date": "Date has wrong format. Use one of these formats instead: YYYY-MM-DD."
        }

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_absent_issue_date(self):
        data = {"issue_number": "ADS-TEST-DATE"}
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {"issue_date": "This field is required."}

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_bdg_rnbid(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDG-DOES-NOT-EXIST"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = 'Building "BDG-DOES-NOT-EXIST" does not exist.'

        for op in r_data["buildings_operations"]:
            if "building" in op:
                if "rnb_id" in op["building"]:
                    self.assertIn(msg_to_check, op["building"]["rnb_id"])

    def test_ads_wrong_operation(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "destroy",
                    "building": {"rnb_id": "BDG-RNB-ID"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = "'destroy' is not a valid operation. Valid operations are: ['build', 'modify', 'demolish']."

        for op in r_data["buildings_operations"]:
            if "operation" in op:
                self.assertIn(msg_to_check, op["operation"])

    def test_ads_absent_lat(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "new"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = "lat field is required for new buildings."

        for op in r_data["buildings_operations"]:
            if "building" in op:
                if "lat" in op["building"]:
                    self.assertIn(msg_to_check, op["building"]["lat"])

    def test_ads_wrong_latlng(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "new", "lat": "hello", "lng": "bonjour"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = "A valid number is required."

        for op in r_data["buildings_operations"]:
            if "building" in op:
                self.assertIn(msg_to_check, op["building"]["lat"])
                self.assertIn(msg_to_check, op["building"]["lng"])

    def test_ads_absent_lng(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "new"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = "lng field is required for new buildings."

        for op in r_data["buildings_operations"]:
            if "building" in op:
                if "lng" in op["building"]:
                    self.assertIn(msg_to_check, op["building"]["lng"])

    # ###############
    # Data setup

    def __insert_data(self):
        # ############
        # Building
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
            rnb_id="BDG-RNB-ID", source="dummy", shape=geom, point=geom.point_on_surface
        )

        # ############
        # ADS
        ads = ADS.objects.create(issue_number="ADS-TEST", issue_date="2019-01-01")

        ADS.objects.create(issue_number="ADS-TEST-FUTURE", issue_date="2025-01-02")

        ADS.objects.create(issue_number="ADS-TEST-UPDATE", issue_date="2025-01-01")
        ADS.objects.create(issue_number="ADS-TEST-UPDATE-BDG", issue_date="2025-01-01")

        # ############
        # BuildingADS
        BuildingADS.objects.create(building=b, ads=ads, operation="build")
