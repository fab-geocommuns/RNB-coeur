import json
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from batid.models import Building, ADS, BuildingADS, Organization


class ADSEnpointsWithBadAuthTest(APITestCase):
    def setUp(self):
        u = User.objects.create_user(
            first_name="Marcel", last_name="Paris", username="paris"
        )

        token = Token.objects.create(user=u)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def test_create_ads(self):
        data = {
            "issue_number": "ADS-TEST-NEW-BDG",
            "issue_date": "2019-03-18",
            "insee_code": "4242",
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

        self.assertEqual(r.status_code, 403)


class ADSEndpointsWithAuthTest(APITestCase):
    def setUp(self):
        self.__insert_data()

    def test_ads_root(self):
        r = self.client.get("/api/alpha/ads/")
        self.assertEqual(r.status_code, 200)

    def test_ads_search_since(self):
        r = self.client.get("/api/alpha/ads/?since=2034-12-01")
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        expected = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "issue_number": "ADS-TEST-FUTURE",
                    "issue_date": "2035-01-02",
                    "insee_code": "12345",
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
                    "issue_date": "2035-01-02",
                    "insee_code": "12345",
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
            "insee_code": "5555",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-RNB-ID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [1.065566769109707, 46.63416324688205],
                        },
                    },
                }
            ],
        }
        self.assertDictEqual(r_data, expected)

    def test_create_simple_ads(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-01",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-RNB-ID",
                    },
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        self.assertEqual(r.status_code, 200)

        expected = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-RNB-ID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [1.065566769109707, 46.63416324688205],
                        },
                    },
                }
            ],
            "insee_code": "4242",
        }
        self.assertDictEqual(r_data, expected)

    def test_read_unknown_ads(self):
        r = self.client.get("/api/alpha/ads/ABSENT-ADS/")
        self.assertEqual(r.status_code, 404)

    def test_create_ads(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "insee_code": "4242",
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
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-RNB-ID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [1.065566769109707, 46.63416324688205],
                        },
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

    def test_ads_create_with_new_bdg_mp(self):
        data = {
            "issue_number": "ADS-TEST-NEW-BDG-MP",
            "issue_date": "2019-03-18",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "coordinates": [
                                [
                                    [
                                        [5.736498177543439, 45.18740370893255],
                                        [5.736455101954846, 45.18732521910442],
                                        [5.736581176848205, 45.187335585691784],
                                        [5.736620049940626, 45.187404449402266],
                                        [5.736498177543439, 45.18740370893255],
                                    ]
                                ]
                            ],
                            "type": "MultiPolygon",
                        },
                    },
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/alpha/ads/ADS-TEST-NEW-BDG-MP/")
        r_data = r.json()

        new_rnb_id = r_data["buildings_operations"][0]["building"]["rnb_id"]

        expected = {
            "issue_number": "ADS-TEST-NEW-BDG-MP",
            "issue_date": "2019-03-18",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "coordinates": [5.736539944382292, 45.1873696473121],
                            "type": "Point",
                        },
                    },
                }
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_ads_create_with_new_bdg_point(self):
        data = {
            "issue_number": "ADS-TEST-NEW-BDG",
            "issue_date": "2019-03-18",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-0.4617233264741004, 44.7802149854455],
                        },
                    },
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        new_rnb_id = r_data["buildings_operations"][0]["building"]["rnb_id"]

        expected = {
            "issue_number": "ADS-TEST-NEW-BDG",
            "issue_date": "2019-03-18",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-0.461723326474101, 44.78021498544544],
                        },
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

    def test_ads_update_with_new_bdg(self):
        data = {
            "issue_number": "ADS-TEST-UPDATE",
            "issue_date": "2025-01-02",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-0.4617233264741004, 44.7802149854455],
                        },
                    },
                }
            ],
        }

        r = self.client.put(
            "/api/alpha/ads/ADS-TEST-UPDATE/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        new_rnb_id = r_data["buildings_operations"][0]["building"]["rnb_id"]

        expected = {
            "issue_number": "ADS-TEST-UPDATE",
            "issue_date": "2025-01-02",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-0.461723326474101, 44.78021498544544],
                        },
                    },
                }
            ],
        }
        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE/")
        r_data = r.json()
        self.assertDictEqual(r_data, expected)

    def test_ads_update_many_buildings(self):
        data = {
            "issue_number": "ADS-TEST-UPDATE-MANY-BDG",
            "issue_date": "2025-01-01",
            "insee_code": "4242",
            "buildings_operations": [
                {"operation": "modify", "building": {"rnb_id": "BDG-IN-ADS-ONE"}},
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-IN-ADS-TWO",
                    },
                },
            ],
        }
        r = self.client.put(
            "/api/alpha/ads/ADS-TEST-UPDATE-MANY-BDG/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE-MANY-BDG/")
        r_data = r.json()

        expected = {
            "issue_number": "ADS-TEST-UPDATE-MANY-BDG",
            "issue_date": "2025-01-01",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "modify",
                    "building": {
                        "rnb_id": "BDG-IN-ADS-ONE",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [1.065566769109707, 46.63416324688205],
                        },
                    },
                },
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-IN-ADS-TWO",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [1.065566769109707, 46.63416324688205],
                        },
                    },
                },
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_ads_same_bdg_twice(self):
        data = {
            "issue_number": "ADS-TEST-BDG-TWICE",
            "issue_date": "2019-01-02",
            "insee_code": "4242",
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
        data = {
            "issue_number": "ADS-TEST",
            "issue_date": "2019-01-02",
            "insee_code": "4242",
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {"issue_number": "This issue number already exists"}

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_issue_date(self):
        data = {
            "issue_number": "ADS-TEST-DATE",
            "issue_date": "2019-13-01",
            "insee_code": "4242",
        }
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
        data = {"issue_number": "ADS-TEST-DATE", "insee_code": "4242"}
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

    def test_ads_wrong_geometry(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "new", "geometry": "wrong"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = 'Expected a dictionary of items but got type "str".'

        for op in r_data["buildings_operations"]:
            if "building" in op:
                self.assertIn(msg_to_check, op["building"]["geometry"])

    def test_ads_absent_geometry(self):
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

        msg_to_check = "GeoJSON Point or MultiPolygon is required for new buildings."

        for op in r_data["buildings_operations"]:
            if "building" in op:
                if "geometry" in op["building"]:
                    self.assertIn(msg_to_check, op["building"]["geometry"])

    def test_ads_invalid_geometry(self):
        data = {
            "issue_number": "ADS-TEST-2",
            "issue_date": "2019-01-02",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.736498177543439, 45.18740370893255],
                                        [5.736455101954846, 45.18732521910442],
                                        [5.736581176848205, 45.187335585691784],
                                        [5.736620049940626, 45.187404449402266],
                                    ]
                                ]
                            ],
                        },
                    },
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

        # ###############
        # Data setup

    def test_ads_delete_yes(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST-DELETE-YES/")
        self.assertEqual(r.status_code, 200)

        r = self.client.delete("/api/alpha/ads/ADS-TEST-DELETE-YES/")
        self.assertEqual(r.status_code, 204)

        r = self.client.get("/api/alpha/ads/ADS-TEST-DELETE-YES/")
        self.assertEqual(r.status_code, 404)

    def test_ads_delete_no(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST-DELETE-NO/")
        self.assertEqual(r.status_code, 200)

        r = self.client.delete("/api/alpha/ads/ADS-TEST-DELETE-NO/")
        self.assertEqual(r.status_code, 403)

        r = self.client.get("/api/alpha/ads/ADS-TEST-DELETE-NO/")
        self.assertEqual(r.status_code, 200)

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

        bdg_ads_one = Building.objects.create(
            rnb_id="BDG-IN-ADS-ONE",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )
        bdg_ads_two = Building.objects.create(
            rnb_id="BDG-IN-ADS-TWO",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )

        # ############
        # ADS
        ads = ADS.objects.create(
            issue_number="ADS-TEST", issue_date="2019-01-01", insee_code="5555"
        )
        BuildingADS.objects.create(building=b, ads=ads, operation="build")

        ADS.objects.create(
            issue_number="ADS-TEST-FUTURE", issue_date="2035-01-02", insee_code="12345"
        )

        ADS.objects.create(
            issue_number="ADS-TEST-UPDATE", issue_date="2025-01-01", insee_code="4242"
        )
        ADS.objects.create(
            issue_number="ADS-TEST-UPDATE-BDG",
            issue_date="2025-01-01",
            insee_code="4242",
        )

        ADS.objects.create(
            issue_number="ADS-TEST-DELETE-YES",
            issue_date="2025-01-01",
            insee_code="4242",
        )
        ADS.objects.create(
            issue_number="ADS-TEST-DELETE-NO",
            issue_date="2025-01-01",
            insee_code="94170",
        )

        # For many buildings in one ADS (for update and delete test)
        many_bdg_ads = ADS.objects.create(
            issue_number="ADS-TEST-UPDATE-MANY-BDG",
            issue_date="2025-01-01",
            insee_code="4242",
        )
        BuildingADS.objects.create(
            building=bdg_ads_one, ads=many_bdg_ads, operation="build"
        )
        BuildingADS.objects.create(
            building=bdg_ads_two, ads=many_bdg_ads, operation="demolish"
        )

        # User, Org & Token
        u = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe"
        )
        org = Organization.objects.create(name="Test Org", managed_cities=["4242"])
        org.users.add(u)

        token = Token.objects.create(user=u)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)


class ADSEnpointsNoAuthTest(APITestCase):
    def setUp(self) -> None:
        ADS.objects.create(
            issue_number="ADS-TEST-UPDATE-BDG",
            issue_date="2025-01-01",
            insee_code="4242",
        )

        ADS.objects.create(
            issue_number="ADS-TEST-DELETE",
            issue_date="2025-01-01",
            insee_code="4242",
        )

    def test_ads_root(self):
        r = self.client.get("/api/alpha/ads/")
        self.assertEqual(r.status_code, 200)

    def test_ads_detail(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE-BDG/")
        self.assertEqual(r.status_code, 200)

    def test_ads_cant_delete(self):
        r = self.client.delete("/api/alpha/ads/ADS-TEST-DELETE/")

        self.assertEqual(r.status_code, 401)
