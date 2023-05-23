import json
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from batid.models import Building, ADS, BuildingADS, Organization, City


class ADSEnpointsWithBadAuthTest(APITestCase):
    def setUp(self):
        u = User.objects.create_user(
            first_name="Marcel", last_name="Paris", username="paris"
        )

        token = Token.objects.create(user=u)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def test_create_ads(self):
        data = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decision_date": "2019-03-18",
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
                    "file_number": "ADS-TEST-FUTURE",
                    "decision_date": "2035-01-02",
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
                    "file_number": "ADS-TEST-FUTURE",
                    "decision_date": "2035-01-02",
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
            "file_number": "ADS-TEST",
            "decision_date": "2019-01-01",
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDG-RNB-ID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718191258820704, 45.17874138804159],
                        },
                    },
                }
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_create_simple_ads(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-01",
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
        print(r_data)

        self.assertEqual(r.status_code, 200)

        expected = {
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-01",
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
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
        }
        self.assertDictEqual(r_data, expected)

    def test_read_unknown_ads(self):
        r = self.client.get("/api/alpha/ads/ABSENT-ADS/")
        self.assertEqual(r.status_code, 404)

    def test_create_ads(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-NEW-BDG-MP",
            "decision_date": "2019-03-18",
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
            "file_number": "ADS-TEST-NEW-BDG-MP",
            "decision_date": "2019-03-18",
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
            "file_number": "ADS-TEST-NEW-BDG",
            "decision_date": "2019-03-18",
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
            "file_number": "ADS-TEST-NEW-BDG",
            "decision_date": "2019-03-18",
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
            "file_number": "ADS-TEST-UPDATE",
            "decision_date": "2025-01-02",
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
            "file_number": "ADS-TEST-UPDATE",
            "decision_date": "2025-01-02",
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
            "file_number": "ADS-TEST-UPDATE-MANY-BDG",
            "decision_date": "2025-01-01",
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
            "file_number": "ADS-TEST-UPDATE-MANY-BDG",
            "decision_date": "2025-01-01",
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
            "file_number": "ADS-TEST-BDG-TWICE",
            "decision_date": "2019-01-02",
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

    def test_ads_wrong_file_number(self):
        data = {
            "file_number": "ADS-TEST",
            "decision_date": "2019-01-02",
            "insee_code": "4242",
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {"file_number": "This issue number already exists"}

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_decision_date(self):
        data = {
            "file_number": "ADS-TEST-DATE",
            "decision_date": "2019-13-01",
            "insee_code": "4242",
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {
            "decision_date": "Date has wrong format. Use one of these formats instead: YYYY-MM-DD."
        }

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_absent_decision_date(self):
        data = {"file_number": "ADS-TEST-DATE", "insee_code": "4242"}
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {"decision_date": "This field is required."}

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_bdg_rnbid(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
            "file_number": "ADS-TEST-2",
            "decision_date": "2019-01-02",
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
        # Cities
        grenoble = create_grenoble()

        # ############
        # Building
        coords = {
            "coordinates": [
                [
                    [
                        [5.717918517856731, 45.178820091145724],
                        [5.718008279271032, 45.17865980057857],
                        [5.7184092135875915, 45.17866401875747],
                        [5.7184451181529425, 45.17884961830637],
                        [5.717924501950705, 45.17893819969589],
                        [5.717918517856731, 45.178820091145724],
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
        ads = ADS.objects.create(file_number="ADS-TEST", decision_date="2019-01-01")
        BuildingADS.objects.create(building=b, ads=ads, operation="build")

        ADS.objects.create(
            file_number="ADS-TEST-FUTURE", decision_date="2035-01-02", city=grenoble
        )

        ADS.objects.create(
            file_number="ADS-TEST-UPDATE",
            decision_date="2025-01-01",
            city=grenoble,
        )
        ADS.objects.create(
            file_number="ADS-TEST-UPDATE-BDG",
            decision_date="2025-01-01",
            city=grenoble,
        )

        ADS.objects.create(
            file_number="ADS-TEST-DELETE-YES",
            decision_date="2025-01-01",
            city=grenoble,
        )
        ADS.objects.create(
            file_number="ADS-TEST-DELETE-NO",
            decision_date="2025-01-01",
            city=grenoble,
        )

        # For many buildings in one ADS (for update and delete test)
        many_bdg_ads = ADS.objects.create(
            file_number="ADS-TEST-UPDATE-MANY-BDG",
            decision_date="2025-01-01",
            city=grenoble,
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
            file_number="ADS-TEST-UPDATE-BDG",
            decision_date="2025-01-01",
            insee_code="4242",
        )

        ADS.objects.create(
            file_number="ADS-TEST-DELETE",
            decision_date="2025-01-01",
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


def create_grenoble():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [5.678683, 45.213686],
                    [5.679474, 45.214319],
                    [5.68056, 45.213597],
                    [5.682558, 45.21246],
                    [5.683693, 45.212032],
                    [5.685226, 45.211695],
                    [5.688486, 45.210987],
                    [5.695176, 45.209975],
                    [5.69887, 45.20861],
                    [5.702106, 45.207509],
                    [5.703666, 45.206955],
                    [5.705088, 45.206436],
                    [5.70624, 45.205961],
                    [5.70689, 45.205744],
                    [5.707702, 45.205551],
                    [5.709353, 45.205181],
                    [5.709839, 45.205055],
                    [5.710186, 45.204929],
                    [5.710829, 45.204623],
                    [5.711085, 45.204449],
                    [5.713141, 45.202975],
                    [5.713655, 45.202574],
                    [5.713938, 45.202307],
                    [5.714478, 45.201734],
                    [5.714772, 45.20139],
                    [5.715034, 45.200977],
                    [5.715193, 45.200679],
                    [5.715403, 45.200067],
                    [5.715465, 45.199829],
                    [5.715458, 45.199612],
                    [5.717848, 45.199787],
                    [5.717819, 45.199913],
                    [5.720918, 45.199238],
                    [5.720951, 45.199052],
                    [5.721985, 45.198795],
                    [5.721937, 45.198655],
                    [5.722024, 45.19854],
                    [5.722582, 45.19855],
                    [5.72302, 45.198392],
                    [5.723067, 45.198303],
                    [5.723694, 45.198557],
                    [5.723767, 45.19839],
                    [5.723885, 45.198399],
                    [5.723805, 45.19869],
                    [5.724511, 45.198753],
                    [5.724486, 45.198933],
                    [5.724928, 45.198909],
                    [5.725515, 45.199656],
                    [5.725313, 45.200307],
                    [5.725128, 45.200506],
                    [5.725244, 45.200651],
                    [5.725183, 45.201135],
                    [5.724433, 45.202351],
                    [5.724845, 45.20418],
                    [5.725715, 45.205014],
                    [5.731737, 45.202213],
                    [5.733524, 45.201845],
                    [5.733816, 45.201947],
                    [5.734103, 45.201791],
                    [5.734894, 45.201271],
                    [5.735523, 45.201695],
                    [5.735877, 45.2019],
                    [5.736402, 45.202116],
                    [5.73669, 45.202184],
                    [5.73695, 45.20221],
                    [5.737685, 45.202206],
                    [5.738058, 45.202169],
                    [5.739103, 45.201941],
                    [5.739351, 45.201853],
                    [5.739697, 45.201659],
                    [5.741082, 45.200846],
                    [5.741421, 45.200568],
                    [5.741915, 45.200105],
                    [5.742276, 45.199599],
                    [5.742582, 45.19909],
                    [5.742916, 45.198354],
                    [5.743132, 45.197793],
                    [5.743245, 45.197201],
                    [5.743262, 45.196799],
                    [5.743162, 45.196083],
                    [5.743082, 45.195768],
                    [5.742904, 45.195316],
                    [5.742506, 45.19445],
                    [5.742169, 45.193779],
                    [5.741982, 45.193318],
                    [5.741924, 45.193097],
                    [5.741794, 45.192466],
                    [5.741789, 45.192232],
                    [5.741931, 45.191565],
                    [5.742048, 45.191186],
                    [5.742283, 45.190688],
                    [5.74271, 45.190202],
                    [5.74308, 45.189903],
                    [5.743552, 45.189617],
                    [5.743874, 45.189467],
                    [5.744575, 45.189228],
                    [5.745417, 45.188989],
                    [5.746329, 45.188836],
                    [5.74678, 45.188806],
                    [5.747654, 45.188786],
                    [5.748057, 45.1888],
                    [5.748391, 45.188845],
                    [5.748934, 45.18896],
                    [5.749281, 45.189088],
                    [5.748386, 45.188336],
                    [5.748028, 45.188017],
                    [5.747798, 45.18788],
                    [5.747089, 45.187139],
                    [5.746501, 45.186602],
                    [5.7464, 45.186455],
                    [5.74641, 45.186294],
                    [5.746544, 45.186104],
                    [5.746593, 45.185934],
                    [5.746754, 45.185891],
                    [5.74681, 45.185816],
                    [5.747193, 45.18549],
                    [5.747383, 45.185274],
                    [5.747438, 45.185116],
                    [5.747349, 45.184658],
                    [5.7474, 45.184304],
                    [5.74786, 45.182425],
                    [5.747987, 45.182183],
                    [5.748238, 45.182015],
                    [5.748997, 45.181586],
                    [5.75026, 45.180847],
                    [5.750357, 45.180779],
                    [5.750453, 45.180616],
                    [5.750672, 45.179933],
                    [5.750858, 45.179279],
                    [5.751098, 45.178983],
                    [5.751455, 45.178402],
                    [5.751684, 45.177835],
                    [5.751831, 45.17739],
                    [5.752033, 45.177021],
                    [5.752325, 45.17657],
                    [5.752598, 45.17649],
                    [5.752626, 45.176211],
                    [5.752898, 45.175805],
                    [5.753078, 45.175627],
                    [5.752851, 45.175395],
                    [5.752709, 45.175126],
                    [5.752375, 45.173991],
                    [5.751925, 45.17272],
                    [5.751495, 45.171637],
                    [5.751375, 45.171531],
                    [5.751267, 45.17133],
                    [5.751187, 45.171107],
                    [5.751027, 45.170831],
                    [5.750592, 45.170175],
                    [5.750458, 45.169906],
                    [5.750282, 45.169659],
                    [5.750037, 45.16951],
                    [5.749985, 45.169358],
                    [5.749812, 45.16923],
                    [5.749725, 45.168897],
                    [5.749185, 45.169068],
                    [5.747153, 45.169821],
                    [5.745983, 45.171052],
                    [5.745751, 45.171285],
                    [5.745621, 45.171498],
                    [5.745422, 45.171593],
                    [5.745118, 45.170196],
                    [5.744785, 45.169309],
                    [5.744153, 45.168338],
                    [5.743949, 45.16812],
                    [5.743022, 45.166374],
                    [5.74124, 45.166798],
                    [5.740799, 45.165659],
                    [5.741226, 45.165531],
                    [5.741387, 45.16523],
                    [5.740982, 45.164723],
                    [5.740933, 45.164473],
                    [5.741424, 45.164094],
                    [5.74086, 45.1637],
                    [5.740294, 45.163239],
                    [5.740148, 45.162879],
                    [5.739846, 45.161246],
                    [5.739918, 45.160662],
                    [5.739793, 45.159849],
                    [5.738975, 45.159606],
                    [5.73755, 45.159309],
                    [5.737257, 45.158023],
                    [5.737025, 45.158016],
                    [5.73716, 45.155879],
                    [5.737696, 45.155859],
                    [5.737768, 45.154206],
                    [5.734862, 45.154148],
                    [5.734818, 45.155119],
                    [5.733811, 45.155097],
                    [5.733759, 45.154886],
                    [5.733117, 45.154792],
                    [5.731757, 45.154792],
                    [5.731654, 45.157285],
                    [5.730511, 45.157407],
                    [5.730331, 45.158884],
                    [5.729056, 45.158853],
                    [5.728956, 45.159166],
                    [5.727963, 45.159182],
                    [5.726137, 45.159224],
                    [5.723451, 45.159531],
                    [5.722053, 45.15977],
                    [5.721194, 45.160022],
                    [5.720192, 45.160076],
                    [5.720173, 45.159762],
                    [5.720028, 45.159171],
                    [5.719367, 45.159079],
                    [5.715083, 45.158927],
                    [5.714343, 45.158865],
                    [5.713224, 45.15885],
                    [5.710929, 45.158761],
                    [5.710239, 45.158525],
                    [5.710031, 45.15841],
                    [5.709334, 45.158574],
                    [5.708894, 45.158654],
                    [5.708315, 45.15871],
                    [5.707729, 45.158731],
                    [5.706145, 45.158737],
                    [5.704329, 45.158708],
                    [5.703524, 45.158659],
                    [5.703124, 45.158711],
                    [5.702816, 45.158823],
                    [5.702198, 45.159145],
                    [5.701765, 45.159383],
                    [5.701312, 45.159582],
                    [5.70102, 45.159616],
                    [5.70021, 45.160251],
                    [5.699699, 45.160431],
                    [5.699797, 45.160733],
                    [5.699949, 45.161116],
                    [5.70011, 45.161666],
                    [5.700181, 45.161826],
                    [5.700353, 45.162046],
                    [5.700574, 45.162236],
                    [5.700694, 45.162436],
                    [5.700791, 45.162701],
                    [5.700926, 45.163471],
                    [5.700947, 45.163983],
                    [5.700855, 45.164746],
                    [5.700878, 45.166757],
                    [5.700761, 45.167457],
                    [5.700504, 45.168301],
                    [5.700491, 45.168778],
                    [5.700666, 45.170801],
                    [5.700741, 45.171081],
                    [5.701149, 45.17156],
                    [5.70123, 45.171763],
                    [5.700787, 45.172307],
                    [5.700742, 45.172625],
                    [5.700973, 45.173733],
                    [5.701017, 45.1748],
                    [5.701134, 45.17574],
                    [5.701275, 45.176747],
                    [5.701077, 45.177099],
                    [5.700873, 45.177351],
                    [5.700841, 45.177641],
                    [5.700869, 45.178589],
                    [5.70099, 45.179984],
                    [5.701156, 45.179984],
                    [5.701195, 45.180129],
                    [5.70125, 45.181322],
                    [5.701248, 45.182285],
                    [5.701336, 45.182973],
                    [5.701393, 45.185075],
                    [5.701543, 45.187863],
                    [5.701626, 45.189223],
                    [5.701642, 45.190762],
                    [5.701775, 45.193327],
                    [5.701731, 45.193696],
                    [5.701523, 45.194525],
                    [5.701387, 45.195158],
                    [5.701288, 45.195382],
                    [5.700549, 45.19664],
                    [5.700229, 45.197087],
                    [5.699976, 45.197338],
                    [5.699629, 45.197627],
                    [5.699296, 45.197881],
                    [5.698691, 45.198272],
                    [5.698284, 45.198484],
                    [5.69457, 45.200951],
                    [5.693086, 45.202018],
                    [5.68781, 45.20591],
                    [5.678003, 45.213141],
                    [5.678683, 45.213686],
                ]
            ]
        ],
    }
    geom = GEOSGeometry(json.dumps(geometry), srid=4326)
    geom.transform(settings.DEFAULT_SRID)

    return City.objects.create(name="Grenoble", shape=geom, code_insee="38185")
