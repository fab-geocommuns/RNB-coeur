import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import ADS
from batid.models import Building
from batid.models import BuildingADS
from batid.models import Organization
from batid.tests.helpers import create_cenac
from batid.tests.helpers import create_grenoble
from batid.tests.helpers import create_paris


class ADSEnpointsWithBadAuthTest(APITestCase):
    def setUp(self):
        create_paris()

        u = User.objects.create_user(
            first_name="Marcel", last_name="Paris", username="paris"
        )

        token = Token.objects.create(user=u)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def test_create_ads(self):
        # Building is in Paris
        data = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decided_at": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [2.3552747458487002, 48.86958288638419],
                        },
                    },
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 403)


class ADSEndpointsWithAuthTest(APITestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None

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
                    "decided_at": "2035-01-02",
                    "city": {
                        "code_insee": "38185",
                        "name": "Grenoble",
                    },
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
                    "decided_at": "2035-01-02",
                    "city": {
                        "code_insee": "38185",
                        "name": "Grenoble",
                    },
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
            "decided_at": "2019-01-01",
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSRNBBIDID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
                        },
                    },
                }
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_create_simple_ads(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSRNBBIDID",
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
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSRNBBIDID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
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

        # Verify the creator
        ads = ADS.objects.get(file_number="ADS-TEST-2")
        self.assertEqual(ads.creator, self.user)

    # This test needs a refacto of the BuildingsADSSerializer to pass
    # We can follow what the double step validation done in the ADSSerializer with the cities
    # issue :https://github.com/fab-geocommuns/BatID-core/issues/168
    # def test_twice_same_bdg_one_guess(self):
    #     data = {
    #         "file_number": "ADS-TEST-GUESS-NEW-BDG",
    #         "decided_at": "2023-07-19",
    #         "buildings_operations": [
    #             {
    #                 "operation": "build",
    #                 "building": {
    #                     "rnb_id": "guess",
    #                     "geometry": {
    #                         "type": "MultiPolygon",
    #                         "coordinates": [
    #                             [
    #                                 [
    #                                     [5.727481544742659, 45.18703215564693],
    #                                     [5.726913971918663, 45.18682335805852],
    #                                     [5.727180892471154, 45.186454342625154],
    #                                     [5.727817395327776, 45.18666934350475],
    #                                     [5.727836461081949, 45.18671068973464],
    #                                     [5.727481544742659, 45.18703215564693],
    #                                 ]
    #                             ]
    #                         ],
    #                     },
    #                 },
    #             },
    #             {
    #                 "operation": "build",
    #                 "building": {
    #                     "rnb_id": "GUESSGUESSG2",
    #                 },
    #             },
    #         ],
    #     }
    #
    #     r = self.client.post(
    #         "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
    #     )
    #     data = r.json()
    #
    #     self.assertEqual(r.status_code, 400)
    #     self.assertEqual(
    #         data["buildings_operations"],
    #         ["A building can only be present once in an ADS."],
    #     )

    def test_guess_twice_same_bdg(self):
        data = {
            "file_number": "ADS-TEST-GUESS-NEW-BDG",
            "decided_at": "2023-07-19",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.7268098966978584, 45.18679068601881],
                                        [5.726715493784042, 45.18675856568265],
                                        [5.726765950514107, 45.18668858917246],
                                        [5.72641763631384, 45.1865658432821],
                                        [5.726378573039369, 45.18663237847073],
                                        [5.726284170125581, 45.18659566941048],
                                        [5.726531570865745, 45.18624234350065],
                                        [5.727065435620517, 45.18643391983434],
                                        [5.7268098966978584, 45.18679068601881],
                                    ]
                                ]
                            ],
                        },
                    },
                },
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.7268098966978584, 45.18679068601881],
                                        [5.726715493784042, 45.18675856568265],
                                        [5.726765950514107, 45.18668858917246],
                                        [5.72641763631384, 45.1865658432821],
                                        [5.726378573039369, 45.18663237847073],
                                        [5.726284170125581, 45.18659566941048],
                                        [5.726531570865745, 45.18624234350065],
                                        [5.727065435620517, 45.18643391983434],
                                        [5.7268098966978584, 45.18679068601881],
                                    ]
                                ]
                            ],
                        },
                    },
                },
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        data = r.json()

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            data["buildings_operations"],
            ["A building can only be present once in an ADS."],
        )

    def test_guess_w_point(self):
        data = {
            "file_number": "GUESS-POINT",
            "decided_at": "2023-07-19",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.7268098966978584, 45.18679068601881],
                        },
                    },
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        data = r.json()

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            data["buildings_operations"][0]["building"]["geometry"],
            ["GeoJSON must be a MultiPolygon if you set 'guess' as rnb_id."],
        )

    def test_guess_w_invalid_polygon(self):
        data = {
            "file_number": "GUESS-INVALID",
            "decided_at": "2023-07-19",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.7268098966978584, 45.18679068601881],
                                        [5.726715493784042, 45.18675856568265],
                                        [5.726765950514107, 45.18668858917246],
                                        [5.72641763631384, 45.1865658432821],
                                        [5.726378573039369, 45.18663237847073],
                                        [5.726284170125581, 45.18659566941048],
                                        [5.726531570865745, 45.18624234350065],
                                        [5.727065435620517, 45.18643391983434],
                                        # [5.7268098966978584, 45.18679068601881],
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
        data = r.json()

        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            data["buildings_operations"][0]["building"]["geometry"],
            ["GeoJSON is invalid."],
        )

        # First we verify the ADS contains only one building
        r = self.client.get("/api/alpha/ads/MODIFY-GUESS/")
        data = r.json()

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data["buildings_operations"]), 1)
        self.assertEqual(
            data["buildings_operations"][0]["building"]["rnb_id"], "BDGSRNBBIDID"
        )

        # Then we modify the ADS to guess one building
        data = {
            "file_number": "MODIFY-GUESS",
            "decided_at": "2023-07-19",
            "buildings_operations": [
                {"operation": "build", "building": {"rnb_id": "BDGSRNBBIDID"}},
                {
                    "operation": "demolish",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.727481544742659, 45.18703215564693],
                                        [5.726913971918663, 45.18682335805852],
                                        [5.727180892471154, 45.186454342625154],
                                        [5.727817395327776, 45.18666934350475],
                                        [5.727836461081949, 45.18671068973464],
                                        [5.727481544742659, 45.18703215564693],
                                    ]
                                ]
                            ],
                        },
                    },
                },
            ],
        }

        r = self.client.put(
            "/api/alpha/ads/MODIFY-GUESS/",
            data=json.dumps(data),
            content_type="application/json",
        )

        data = r.json()

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data["buildings_operations"]), 2)

        # We verify we have the right buildings in the right order
        self.assertEqual(
            data["buildings_operations"][0]["building"]["rnb_id"], "BDGSRNBBIDID"
        )
        self.assertEqual(
            data["buildings_operations"][1]["building"]["rnb_id"], "GUESSGUESSG2"
        )

    def test_create_with_guess_new_bdg(self):
        data = {
            "file_number": "ADS-TEST-GUESS-NEW-BDG",
            "decided_at": "2023-07-19",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.7268098966978584, 45.18679068601881],
                                        [5.726715493784042, 45.18675856568265],
                                        [5.726765950514107, 45.18668858917246],
                                        [5.72641763631384, 45.1865658432821],
                                        [5.726378573039369, 45.18663237847073],
                                        [5.726284170125581, 45.18659566941048],
                                        [5.726531570865745, 45.18624234350065],
                                        [5.727065435620517, 45.18643391983434],
                                        [5.7268098966978584, 45.18679068601881],
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
        data = r.json()
        new_rnb_id = data["buildings_operations"][0]["building"]["rnb_id"]

        # We need to round because there is a precision difference between the local env and the github CI
        rounded_lng = round(
            data["buildings_operations"][0]["building"]["geometry"]["coordinates"][0],
            15,
        )
        rounded_lat = round(
            data["buildings_operations"][0]["building"]["geometry"]["coordinates"][1],
            15,
        )

        expected = {
            "file_number": "ADS-TEST-GUESS-NEW-BDG",
            "decided_at": "2023-07-19",
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [rounded_lng, rounded_lat],
                        },
                    },
                }
            ],
        }

        self.maxDiff = None

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(data, expected)

    def test_create_with_guess_bdg(self):
        self.maxDiff = None

        data = {
            "file_number": "ADS-TEST-GUESS-BDG",
            "decided_at": "2023-07-17",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "guess",
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [5.727677616548021, 45.18650547532101],
                                        [5.726661353775256, 45.18614386549888],
                                        [5.726875130733703, 45.18586106647285],
                                        [5.727891393506468, 45.18620181594525],
                                        [5.727677616548021, 45.18650547532101],
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

        data = r.json()

        # We need to round because there is a precision difference between the local env and the github CI
        rounded_lng = round(
            data["buildings_operations"][0]["building"]["geometry"]["coordinates"][0],
            15,
        )
        rounded_lat = round(
            data["buildings_operations"][0]["building"]["geometry"]["coordinates"][1],
            15,
        )

        expected = {
            "file_number": "ADS-TEST-GUESS-BDG",
            "decided_at": "2023-07-17",
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "GUESSGUESSGO",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [rounded_lng, rounded_lat],
                        },
                    },
                }
            ],
        }

        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(data, expected)

    def test_create_with_custom_id(self):
        data = {
            "file_number": "CUSTOM-ID",
            "decided_at": "2023-05-12",
            "buildings_operations": [
                {
                    "building": {
                        "rnb_id": "new",
                        "custom_id": "OUR-BDG",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.724331358994107, 45.18157371019683],
                        },
                    },
                    "operation": "build",
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        self.assertEqual(r.status_code, 200)

        expected = {
            "file_number": "CUSTOM-ID",
            "decided_at": "2023-05-12",
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
            "buildings_operations": [
                {
                    "building": {
                        "rnb_id": r_data["buildings_operations"][0]["building"][
                            "rnb_id"
                        ],
                        "custom_id": "OUR-BDG",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.724331358994107, 45.18157371019683],
                        },
                    },
                    "operation": "build",
                }
            ],
        }
        self.assertDictEqual(r_data, expected)

    def test_new_point_in_grenoble(self):
        data = {
            "file_number": "zef",
            "decided_at": "2023-05-12",
            "buildings_operations": [
                {
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.724331358994107, 45.18157371019683],
                        },
                    },
                    "operation": "build",
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 200)

    def test_read_unknown_ads(self):
        r = self.client.get("/api/alpha/ads/ABSENT-ADS/")
        self.assertEqual(r.status_code, 404)

    def test_create_ads_with_dash(self):
        data = {
            "file_number": "ADS-TEST-DASH",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDGS-RNBB-IDID"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        expected = {
            "file_number": "ADS-TEST-DASH",
            "decided_at": "2019-01-02",
            "city": {"name": "Grenoble", "code_insee": "38185"},
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSRNBBIDID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
                        },
                    },
                }
            ],
        }

        # Assert that the response is correct
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 200)

        # Assert that the data is correctly saved
        r = self.client.get("/api/alpha/ads/ADS-TEST-DASH/")
        r_data = r.json()
        self.assertDictEqual(r_data, expected)

    def test_create_ads(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDGSRNBBIDID"},
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        expected = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
            "city": {"name": "Grenoble", "code_insee": "38185"},
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSRNBBIDID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
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
            "decided_at": "2019-03-18",
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
            "decided_at": "2019-03-18",
            "city": {"name": "Grenoble", "code_insee": "38185"},
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "coordinates": [5.736539944382292, 45.18736964731217],
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
            "decided_at": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.717771597834023, 45.17739684209898],
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

        # We need to round because there is a precision difference between the local env and the github CI
        rounded_lng = round(
            r_data["buildings_operations"][0]["building"]["geometry"]["coordinates"][0],
            15,
        )
        rounded_lat = round(
            r_data["buildings_operations"][0]["building"]["geometry"]["coordinates"][1],
            15,
        )

        expected = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decided_at": "2019-03-18",
            "city": {
                "name": "Grenoble",
                "code_insee": "38185",
            },
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [rounded_lng, rounded_lat],
                        },
                    },
                }
            ],
        }
        self.maxDiff = None
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
            "decided_at": "2025-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.720861502527286, 45.18380982645842],
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
            "decided_at": "2025-01-02",
            "city": {"name": "Grenoble", "code_insee": "38185"},
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": new_rnb_id,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.720861502527286, 45.18380982645842],
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
            "decided_at": "2025-01-01",
            "buildings_operations": [
                {"operation": "modify", "building": {"rnb_id": "BDGSADSSONE1"}},
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSADSSTWO2",
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
            "decided_at": "2025-01-01",
            "city": {"name": "Grenoble", "code_insee": "38185"},
            "buildings_operations": [
                {
                    "operation": "modify",
                    "building": {
                        "rnb_id": "BDGSADSSONE1",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
                        },
                    },
                },
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSADSSTWO2",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
                        },
                    },
                },
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_ads_same_bdg_twice(self):
        data = {
            "file_number": "ADS-TEST-BDG-TWICE",
            "decided_at": "2019-01-02",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDGSRNBBIDID"},
                },
                {
                    "operation": "build",
                    "building": {"rnb_id": "BDGSRNBBIDID"},
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
            "decided_at": "2019-01-02",
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

    def test_ads_wrong_decided_at(self):
        data = {
            "file_number": "ADS-TEST-DATE",
            "decided_at": "2019-13-01",
            "insee_code": "4242",
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {
            "decided_at": "Date has wrong format. Use one of these formats instead: YYYY-MM-DD."
        }

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_absent_decided_at(self):
        data = {"file_number": "ADS-TEST-DATE", "insee_code": "4242"}
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = {"decided_at": "This field is required."}

        for key, msg in r_data.items():
            self.assertIn(msg_to_check[key], r_data[key])

    def test_ads_wrong_bdg_rnbid(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
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
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "destroy",
                    "building": {"rnb_id": "BDGSRNBBIDID"},
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
            "decided_at": "2019-01-02",
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
            "decided_at": "2019-01-02",
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
            "decided_at": "2019-01-02",
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
            "decided_at": "2019-01-02",
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

    def test_inoffensive_city(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST/")

        altered_data = r.json()
        altered_data["city"] = {"name": "Paris", "code_insee": "75056"}

        r = self.client.put(
            "/api/alpha/ads/ADS-TEST/",
            data=json.dumps(altered_data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/alpha/ads/ADS-TEST/")
        self.assertEqual(r.status_code, 200)

        expected = {
            "file_number": "ADS-TEST",
            "decided_at": "2019-01-01",
            "city": {"name": "Grenoble", "code_insee": "38185"},
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "BDGSRNBBIDID",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [5.718193263660067, 45.1787420549516],
                        },
                    },
                }
            ],
        }

        self.assertEqual(r.json(), expected)

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

    def test_batch_create(self):
        data = [
            {
                "file_number": "ADS-TEST-BATCH-1",
                "decided_at": "2019-01-02",
                "buildings_operations": [
                    {
                        "operation": "build",
                        "building": {
                            "rnb_id": "new",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [5.718634111400531, 45.183134802624544],
                            },
                        },
                    }
                ],
            },
            {
                "file_number": "ADS-TEST-BATCH-2",
                "decided_at": "2019-01-02",
                "buildings_operations": [
                    {
                        "operation": "build",
                        "building": {
                            "rnb_id": "new",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [5.718254905289841, 45.18335144905792],
                            },
                        },
                    }
                ],
            },
        ]

        r = self.client.post(
            "/api/alpha/ads/batch/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/alpha/ads/ADS-TEST-BATCH-1/")
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/alpha/ads/ADS-TEST-BATCH-2/")
        self.assertEqual(r.status_code, 200)

    def test_batch_update(self):
        existing = ADS.objects.get(file_number="BATCH-UPDATE").id

        data = [
            {
                "file_number": "BATCH-UPDATE",
                "decided_at": "2019-01-02",
                "buildings_operations": [
                    {
                        "operation": "build",
                        "building": {
                            "rnb_id": "BDGSRNBBIDID",
                        },
                    }
                ],
            },
            {
                "file_number": "BATCH-UP-NEW",
                "decided_at": "2019-01-02",
                "buildings_operations": [
                    {
                        "operation": "build",
                        "building": {
                            "rnb_id": "BDGSADSSONE1",
                        },
                    }
                ],
            },
        ]

        r = self.client.post(
            "/api/alpha/ads/batch/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # We check there is still the same id
        kept_id = ADS.objects.get(file_number="BATCH-UPDATE").id

        r = self.client.get("/api/alpha/ads/BATCH-UPDATE/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual("2019-01-02", data["decided_at"])

        self.assertEqual(existing, kept_id)

    def test_empty_batch(self):
        data = []
        r = self.client.post(
            "/api/alpha/ads/batch/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

    def __insert_data(self):
        # ############
        # Cities
        grenoble = create_grenoble()
        create_paris()
        cenac = create_cenac()

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

        # Grenoble
        b = Building.objects.create(
            rnb_id="BDGSRNBBIDID",
            shape=geom,
            point=geom.point_on_surface,
        )

        bdg_ads_one = Building.objects.create(
            rnb_id="BDGSADSSONE1",
            shape=geom,
            point=geom.point_on_surface,
        )
        bdg_ads_two = Building.objects.create(
            rnb_id="BDGSADSSTWO2",
            shape=geom,
            point=geom.point_on_surface,
        )

        # Building for the guess option
        coords = {
            "coordinates": [
                [
                    [
                        [5.727677616548021, 45.18650547532101],
                        [5.726661353775256, 45.18614386549888],
                        [5.726875130733703, 45.18586106647285],
                        [5.727891393506468, 45.18620181594525],
                        [5.727677616548021, 45.18650547532101],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)

        to_guess_bdg = Building.objects.create(
            rnb_id="GUESSGUESSGO",
            shape=geom,
            point=geom.point_on_surface,
        )

        coords = {
            "coordinates": [
                [
                    [
                        [5.727481544742659, 45.18703215564693],
                        [5.726913971918663, 45.18682335805852],
                        [5.727180892471154, 45.186454342625154],
                        [5.727817395327776, 45.18666934350475],
                        [5.727836461081949, 45.18671068973464],
                        [5.727481544742659, 45.18703215564693],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        to_guess_bdg_two = Building.objects.create(
            rnb_id="GUESSGUESSG2",
            shape=geom,
            point=geom.point_on_surface,
        )

        # ############
        # ADS
        ads = ADS.objects.create(
            city=grenoble, file_number="BATCH-UPDATE", decided_at="2019-01-01"
        )
        BuildingADS.objects.create(building=b, ads=ads, operation="build")

        ads = ADS.objects.create(
            city=grenoble, file_number="MODIFY-GUESS", decided_at="2019-01-01"
        )
        BuildingADS.objects.create(building=b, ads=ads, operation="build")

        ads = ADS.objects.create(
            city=grenoble, file_number="ADS-TEST", decided_at="2019-01-01"
        )
        BuildingADS.objects.create(building=b, ads=ads, operation="build")

        ADS.objects.create(
            file_number="ADS-TEST-FUTURE", decided_at="2035-01-02", city=grenoble
        )

        ADS.objects.create(
            file_number="ADS-TEST-UPDATE",
            decided_at="2025-01-01",
            city=grenoble,
        )
        ADS.objects.create(
            file_number="ADS-TEST-UPDATE-BDG",
            decided_at="2025-01-01",
            city=grenoble,
        )

        ADS.objects.create(
            file_number="ADS-TEST-DELETE-YES",
            decided_at="2025-01-01",
            city=grenoble,
        )
        ADS.objects.create(
            file_number="ADS-TEST-DELETE-NO",
            decided_at="2025-01-01",
            city=cenac,
        )

        # For many buildings in one ADS (for update and delete test)
        many_bdg_ads = ADS.objects.create(
            file_number="ADS-TEST-UPDATE-MANY-BDG",
            decided_at="2025-01-01",
            city=grenoble,
        )
        BuildingADS.objects.create(
            building=bdg_ads_one, ads=many_bdg_ads, operation="build"
        )
        BuildingADS.objects.create(
            building=bdg_ads_two, ads=many_bdg_ads, operation="demolish"
        )

        # User, Org & Token
        self.user = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe"
        )
        org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
        org.users.add(self.user)

        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)


class ADSEnpointsNoAuthTest(APITestCase):
    def setUp(self) -> None:
        grenoble = create_grenoble()

        ADS.objects.create(
            file_number="ADS-TEST-UPDATE-BDG", decided_at="2025-01-01", city=grenoble
        )

        ADS.objects.create(
            file_number="ADS-TEST-DELETE", decided_at="2025-01-01", city=grenoble
        )

    def test_ads_root(self):
        r = self.client.get("/api/alpha/ads/")
        self.assertEqual(r.status_code, 401)

    def test_ads_detail(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE-BDG/")
        self.assertEqual(r.status_code, 401)

    def test_ads_cant_delete(self):
        r = self.client.delete("/api/alpha/ads/ADS-TEST-DELETE/")

        self.assertEqual(r.status_code, 401)
