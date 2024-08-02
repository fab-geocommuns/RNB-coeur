import json

from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import ADS
from batid.models import Building
from batid.models import BuildingADS
from batid.models import Organization
from batid.tests.helpers import create_cenac
from batid.tests.helpers import create_from_geojson_feature
from batid.tests.helpers import create_grenoble
from batid.tests.helpers import create_paris
from batid.utils.constants import ADS_GROUP_NAME


class ADSEnpointsWithBadAuthTest(APITestCase):
    def setUp(self):
        create_paris()
        create_grenoble()

        # Marcel has rights on Grenoble but not on Paris
        user = User.objects.create_user(
            first_name="Marcel", last_name="Grenoble", username="grenoble_master"
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        # Add permission
        group, created = Group.objects.get_or_create(name=ADS_GROUP_NAME)
        user.groups.add(group)
        content_type = ContentType.objects.get_for_model(ADS)
        permissions = Permission.objects.filter(content_type=content_type)
        for permission in permissions:
            group.permissions.add(permission)

        org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
        org.users.add(user)

        # Create an ADS set in Grenoble (managed)
        create_from_geojson_feature(
            {
                "type": "Feature",
                "properties": {"rnb_id": "GRENOBLEGOGO"},
                "geometry": {
                    "coordinates": [
                        [
                            [5.72657595080662, 45.18656079765091],
                            [5.72657595080662, 45.18627000138551],
                            [5.727143678224422, 45.18627000138551],
                            [5.727143678224422, 45.18656079765091],
                            [5.72657595080662, 45.18656079765091],
                        ]
                    ],
                    "type": "Polygon",
                },
                "id": 0,
            }
        )

        # ADS in Grenoble
        grenoble_ads = ADS.objects.create(
            file_number="ADS-GRENOBLE",
            decided_at="2019-01-01",
        )
        BuildingADS.objects.create(ads=grenoble_ads, rnb_id="GRENOBLEGOGO")

        # Create a building in Paris
        create_from_geojson_feature(
            {
                "type": "Feature",
                "properties": {"rnb_id": "GOPARISPARIS"},
                "geometry": {
                    "coordinates": [
                        [
                            [2.337174593125127, 48.855123481710905],
                            [2.337174593125127, 48.85417864062413],
                            [2.338546762256243, 48.85417864062413],
                            [2.338546762256243, 48.855123481710905],
                            [2.337174593125127, 48.855123481710905],
                        ]
                    ],
                    "type": "Polygon",
                },
            }
        )

        # Create an ADS set in Parisn (unmanaged)
        paris_ads = ADS.objects.create(
            file_number="ADS-TEST-PARIS",
            decided_at="2020-01-01",
        )
        BuildingADS.objects.create(ads=paris_ads, rnb_id="GOPARISPARIS")

    def test_create_ads_point_in_forbidden_city(self):
        # Building is in Paris
        data = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decided_at": "2020-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": {
                        "type": "Point",
                        "coordinates": [2.3552747458487002, 48.86958288638419],
                    },
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

    def test_create_ads_in_no_city(self):
        data = {
            "file_number": "ADS-TEST-NEW-BDG-LONDON",
            "decided_at": "2020-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": {
                        "type": "Point",
                        "coordinates": [
                            -0.1141407918343872,
                            51.51309174920018,
                        ],  # Londres
                    },
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

    def test_create_ads_rnbid_in_forbidden_city(self):

        data = {
            "file_number": "NEW-ADS-TEST",
            "decided_at": "2020-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "GOPARISPARIS",
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

    def test_update_date_on_ads_forbidden_city(self):

        data = {
            "file_number": "ADS-TEST-PARIS",
            "decided_at": "2022-02-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "GOPARISPARIS",
                }
            ],
        }

        r = self.client.put(
            "/api/alpha/ads/ADS-TEST-PARIS/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 403)

    def test_update_managed_ads_with_forbidden_city_in_request(self):

        data = {
            "file_number": "ADS-GRENOBLE",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "GRENOBLEGOGO",
                },
                {
                    "operation": "build",
                    "rnb_id": "GOPARISPARIS",
                },
            ],
        }

        r = self.client.put(
            "/api/alpha/ads/ADS-GRENOBLE/",
            data=json.dumps(data),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 400)

    def test_view_ads_without_permission(self):
        # The current user's group has all permissions on ADS
        r = self.client.get(
            "/api/alpha/ads/ADS-GRENOBLE/", content_type="application/json"
        )
        self.assertEqual(r.status_code, 200)

        # Remove permission
        permission = Permission.objects.get(codename="view_ads")
        group = Group.objects.get(name=ADS_GROUP_NAME)
        group.permissions.remove(permission)

        r = self.client.get(
            "/api/alpha/ads/ADS-GRENOBLE/", content_type="application/json"
        )
        self.assertEqual(r.status_code, 403)


class ADSEndpointsWithAuthTest(APITestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.token = None
        self.superuser = None
        self.token_superuser = None

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
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                    "shape": None,
                }
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_create_simple_ads(self):
        # This endpoint should not link the building to the ADS

        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        self.assertEqual(r.status_code, 201)

        expected = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {"operation": "build", "rnb_id": "BDGSRNBBIDID", "shape": None}
            ],
        }
        self.assertDictEqual(r_data, expected)

        # Verify the creator
        ads = ADS.objects.get(file_number="ADS-TEST-2")
        self.assertEqual(ads.creator, self.user)

    def test_create_simple_ads_w_two_null_rnb_id(self):
        # This endpoint should not link the building to the ADS

        data = {
            "file_number": "ADS-TEST-3",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.724331358994107, 45.18157371019683],
                    },
                },
                {
                    "operation": "build",
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.824331358994107, 45.28157371019683],
                    },
                },
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        self.assertEqual(r.status_code, 201)

        expected = {
            "file_number": "ADS-TEST-3",
            "decided_at": "2019-01-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": None,
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.724331358994107, 45.18157371019683],
                    },
                },
                {
                    "operation": "build",
                    "rnb_id": None,
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.824331358994107, 45.28157371019683],
                    },
                },
            ],
        }
        self.assertDictEqual(r_data, expected)

        # Verify the creator
        ads = ADS.objects.get(file_number="ADS-TEST-3")
        self.assertEqual(ads.creator, self.user)

    def test_new_point_in_grenoble(self):
        data = {
            "file_number": "zef",
            "decided_at": "2023-05-12",
            "buildings_operations": [
                {
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.724331358994107, 45.18157371019683],
                    },
                    "operation": "build",
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 201)

    def test_read_unknown_ads(self):
        r = self.client.get("/api/alpha/ads/ABSENT-ADS/")
        self.assertEqual(r.status_code, 404)

    def test_create_ads_with_dash(self):
        data = {
            "file_number": "ADS-TEST-DASH",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {"operation": "build", "rnb_id": "BDGS-RNBB-IDID"}
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        expected = {
            "file_number": "ADS-TEST-DASH",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                    "shape": None,
                }
            ],
        }

        # Assert that the response is correct
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 201)

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
                    "rnb_id": "BDGSRNBBIDID",
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
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                    "shape": None,
                }
            ],
        }
        # Assert that the response is correct
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 201)

        # Assert that the data is correctly saved
        r = self.client.get("/api/alpha/ads/ADS-TEST-2/")
        r_data = r.json()
        self.assertDictEqual(r_data, expected)

    def test_create_ads_without_shape_and_rnd_id(self):
        data = {
            "file_number": "ADS-TEST-3",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

        r_data = r.json()
        for op in r_data["buildings_operations"]:
            if "non_field_errors" in op:
                self.assertIn(
                    "Either rnb_id or shape is required.", op["non_field_errors"]
                )

    def test_create_ads_with_shape_and_rnd_id(self):
        data = {
            "file_number": "ADS-TEST-3",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.724331358994107, 45.18157371019683],
                    },
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

        r_data = r.json()
        for op in r_data["buildings_operations"]:
            if "non_field_errors" in op:
                self.assertIn(
                    "You can't provide a rnb_id and a shape, you should remove the shape.",
                    op["non_field_errors"],
                )

    def test_ads_create_with_multipolygon(self):
        data = {
            "file_number": "ADS-TEST-NEW-BDG-MP",
            "decided_at": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": {
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
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 201)

        r = self.client.get("/api/alpha/ads/ADS-TEST-NEW-BDG-MP/")
        r_data = r.json()

        expected = {
            "file_number": "ADS-TEST-NEW-BDG-MP",
            "decided_at": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": None,
                    "shape": {
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
                }
            ],
        }

        self.assertDictEqual(r_data, expected)

    def test_ads_create_with_point(self):
        data = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decided_at": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.717771597834023, 45.17739684209898],
                    },
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        r_data = r.json()

        expected = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decided_at": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": None,
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.717771597834023, 45.17739684209898],
                    },
                }
            ],
        }

        # Assert that the response is correct
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 201)

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
                    "rnb_id": "BDGSADSSTWO2",
                }
            ],
        }

        r = self.client.put(
            "/api/alpha/ads/ADS-TEST-UPDATE/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        # Now, verify that the data has been updated
        expected = {
            "file_number": "ADS-TEST-UPDATE",
            "decided_at": "2025-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSADSSTWO2",
                    "shape": None,
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
                {"operation": "modify", "rnb_id": "BDGSADSSONE1"},
                {
                    "operation": "build",
                    "rnb_id": "BDGSADSSTWO2",
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
            "buildings_operations": [
                {"operation": "modify", "rnb_id": "BDGSADSSONE1", "shape": None},
                {"operation": "build", "rnb_id": "BDGSADSSTWO2", "shape": None},
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
                    "rnb_id": "BDGSRNBBIDID",
                },
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                },
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        self.assertIn(
            "A RNB id can only be present once in an ADS.",
            r_data["buildings_operations"],
        )

    def test_ads_wrong_file_number(self):
        data = {
            "file_number": "ADS-TEST",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                },
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        self.assertIn("This file number already exists", r_data["file_number"])

    def test_ads_wrong_decided_at(self):
        data = {
            "file_number": "ADS-TEST-DATE",
            "decided_at": "2019-13-01",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                },
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        self.assertIn(
            "Date has wrong format. Use one of these formats instead: YYYY-MM-DD.",
            r_data["decided_at"],
        )

    def test_ads_absent_decided_at(self):
        data = {
            "file_number": "ADS-TEST-DATE",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDGSRNBBIDID",
                },
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        self.assertIn("This field is required.", r_data["decided_at"])

    def test_ads_wrong_bdg_rnbid(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "rnb_id": "BDG-DOES-NOT-EXIST",
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = 'Building "BDGDOESNOTEXIST" does not exist.'

        for op in r_data["buildings_operations"]:
            if "rnb_id" in op:
                self.assertIn(msg_to_check, op["rnb_id"])

    def test_ads_wrong_operation(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "destroy",
                    "rnb_id": "BDGSRNBBIDID",
                },
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

    def test_ads_wrong_shape(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": "wrong",
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = "Unable to convert to python object: String input unrecognized as WKT EWKT, and HEXEWKB."

        self.assertIn(msg_to_check, r_data["buildings_operations"][0]["shape"])

    def test_ads_absent_shape_and_rnb_id(self):
        data = {
            "file_number": "ADS-TEST-2",
            "decided_at": "2019-01-02",
            "buildings_operations": [{"operation": "build"}],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

        r_data = r.json()

        msg_to_check = "You must set a RNB ID or a shape for each building operation."

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
                    "rnb_id": "new",
                    "shape": {
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
                }
            ],
        }

        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )
        r_data = r.json()

        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "Invalid format: string or unicode input unrecognized as GeoJSON, WKT EWKT or HEXEWKB.",
            r_data["buildings_operations"][0]["shape"],
        )

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

    def test_ads_create_user_wrong_auth(self):
        data = json.dumps(
            [
                {
                    "username": "johndoe",
                    "email": "test@exemple.fr",
                    "organization_name": "TempOrg",
                    "organization_managed_cities": ["38185"],
                }
            ]
        )

        self.client.credentials()
        r = self.client.post(
            "/api/alpha/ads/token/", data=data, content_type="application/json"
        )
        self.assertEqual(r.status_code, 401)

        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)
        r = self.client.post(
            "/api/alpha/ads/token/", data=data, content_type="application/json"
        )
        self.assertEqual(r.status_code, 403)

    def test_ads_create_user_ok(self):
        username = "john_doe"
        email = "test@exemple.fr"
        organization_name = "TempOrg"
        organization_managed_cities = ["38185"]
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token_superuser.key)
        r = self.client.post(
            "/api/alpha/ads/token/",
            data=json.dumps(
                [
                    {
                        "username": username,
                        "email": email,
                        "organization_name": organization_name,
                        "organization_managed_cities": organization_managed_cities,
                    },
                    {
                        "username": "johndoe",
                        "email": email,
                        "organization_name": organization_name,
                        "organization_managed_cities": organization_managed_cities,
                    },
                ]
            ),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 200)
        r_data = r.json()["created_users"]

        def clean_users_in_response(d):
            return {k: v for k, v in d.items() if k not in ["password", "token"]}

        expected = [
            {
                "username": username,
                "organization_name": organization_name,
                "email": email,
            },
            {
                "username": "johndoe",
                "organization_name": organization_name,
                "email": "",  # This user is already created in the setUp() function without an email. If the user already exists it is returned without being updated. 
            },
        ]

        # Check response
        self.assertListEqual(
            [clean_users_in_response(item) for item in r_data], expected
        )
        self.assertIsNotNone(r_data[0]["token"])
        self.assertIsNotNone(r_data[0]["password"])
        self.assertIsNotNone(r_data[1]["token"])
        self.assertIsNotNone(r_data[1]["password"])

        # Check User in DB
        john = User.objects.get(username=username)
        self.assertEqual(email, john.email)
        self.assertTrue(john.groups.filter(name="ADS").exists())

        # Check Organization in DB
        temp_org = Organization.objects.get(name=organization_name)
        self.assertEqual(organization_managed_cities, temp_org.managed_cities)

        # Check Token in DB
        token = Token.objects.get(user=john)
        self.assertEqual(r_data[0]["token"], token.key)

        # Create an ADS with this new user/token
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        data = {
            "file_number": "ADS-TEST-RIGHT-42",
            "decided_at": "2020-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "shape": {
                        "type": "Point",
                        "coordinates": [5.717771597834023, 45.17739684209898],
                    },
                }
            ],
        }
        r = self.client.post(
            "/api/alpha/ads/", data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(r.status_code, 201)

    # def test_batch_create(self):
    #     data = [
    #         {
    #             "file_number": "ADS-TEST-BATCH-1",
    #             "decided_at": "2019-01-02",
    #             "buildings_operations": [
    #                 {
    #                     "operation": "build",
    #                     "rnb_id": None,
    #                     "shape": {
    #                         "type": "Point",
    #                         "coordinates": [5.718634111400531, 45.183134802624544],
    #                     },
    #                 }
    #             ],
    #         },
    #         {
    #             "file_number": "ADS-TEST-BATCH-2",
    #             "decided_at": "2019-01-02",
    #             "buildings_operations": [
    #                 {
    #                     "operation": "build",
    #                     "rnb_id": None,
    #                     "shape": {
    #                         "type": "Point",
    #                         "coordinates": [5.718254905289841, 45.18335144905792],
    #                     },
    #                 }
    #             ],
    #         },
    #     ]
    #
    #     r = self.client.post(
    #         "/api/alpha/ads/batch/",
    #         data=json.dumps(data),
    #         content_type="application/json",
    #     )
    #
    #     self.assertEqual(r.status_code, 201)
    #
    #     r = self.client.get("/api/alpha/ads/ADS-TEST-BATCH-1/")
    #     self.assertEqual(r.status_code, 200)
    #
    #     r = self.client.get("/api/alpha/ads/ADS-TEST-BATCH-2/")
    #     self.assertEqual(r.status_code, 200)

    # def test_batch_update(self):
    #     existing = ADS.objects.get(file_number="BATCH-UPDATE").id
    #
    #     data = [
    #         {
    #             "file_number": "BATCH-UPDATE",
    #             "decided_at": "2019-01-02",
    #             "buildings_operations": [
    #                 {
    #                     "operation": "build",
    #                     "rnb_id": "BDGSRNBBIDID",
    #                 }
    #             ],
    #         },
    #         {
    #             "file_number": "BATCH-UP-NEW",
    #             "decided_at": "2019-01-02",
    #             "buildings_operations": [
    #                 {
    #                     "operation": "build",
    #                     "rnb_id": "BDGSADSSONE1",
    #                 }
    #             ],
    #         },
    #     ]
    #
    #     r = self.client.post(
    #         "/api/alpha/ads/batch/",
    #         data=json.dumps(data),
    #         content_type="application/json",
    #     )
    #
    #     # We check there is still the same id
    #     kept_id = ADS.objects.get(file_number="BATCH-UPDATE").id
    #
    #     r = self.client.get("/api/alpha/ads/BATCH-UPDATE/")
    #     self.assertEqual(r.status_code, 200)
    #     data = r.json()
    #     self.assertEqual("2019-01-02", data["decided_at"])
    #
    #     self.assertEqual(existing, kept_id)

    # def test_empty_batch(self):
    #     data = []
    #     r = self.client.post(
    #         "/api/alpha/ads/batch/",
    #         data=json.dumps(data),
    #         content_type="application/json",
    #     )
    #
    #     self.assertEqual(r.status_code, 400)

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

        # # Grenoble
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

        # Create a building in Paris
        create_from_geojson_feature(
            {
                "type": "Feature",
                "properties": {"rnb_id": "GOPARISPARIS"},
                "geometry": {
                    "coordinates": [
                        [
                            [2.337174593125127, 48.855123481710905],
                            [2.337174593125127, 48.85417864062413],
                            [2.338546762256243, 48.85417864062413],
                            [2.338546762256243, 48.855123481710905],
                            [2.337174593125127, 48.855123481710905],
                        ]
                    ],
                    "type": "Polygon",
                },
            }
        )

        # ############
        # ADS
        ads = ADS.objects.create(file_number="BATCH-UPDATE", decided_at="2019-01-01")
        BuildingADS.objects.create(rnb_id="BDGSRNBBIDID", ads=ads, operation="build")

        ads = ADS.objects.create(file_number="MODIFY-GUESS", decided_at="2019-01-01")
        BuildingADS.objects.create(rnb_id="BDGSRNBBIDID", ads=ads, operation="build")

        ads = ADS.objects.create(file_number="ADS-TEST", decided_at="2019-01-01")
        BuildingADS.objects.create(rnb_id="BDGSRNBBIDID", ads=ads, operation="build")

        ADS.objects.create(file_number="ADS-TEST-FUTURE", decided_at="2035-01-02")

        ads = ADS.objects.create(
            file_number="ADS-TEST-UPDATE",
            decided_at="2025-01-01",
        )
        BuildingADS.objects.create(rnb_id="BDGSRNBBIDID", ads=ads, operation="build")

        ADS.objects.create(
            file_number="ADS-TEST-UPDATE-BDG",
            decided_at="2025-01-01",
        )

        ads = ADS.objects.create(
            file_number="ADS-TEST-DELETE-YES",
            decided_at="2025-01-01",
        )
        BuildingADS.objects.create(
            rnb_id="BDGSRNBBIDID",
            ads=ads,
            operation="build",
            shape=None,
        )

        ads_in_paris = ADS.objects.create(
            file_number="ADS-TEST-DELETE-NO", decided_at="2025-01-01"
        )
        BuildingADS.objects.create(
            rnb_id="GOPARISPARIS", ads=ads_in_paris, operation="build"
        )

        # For many buildings in one ADS (for update and delete test)
        many_bdg_ads = ADS.objects.create(
            file_number="ADS-TEST-UPDATE-MANY-BDG", decided_at="2025-01-01"
        )
        BuildingADS.objects.create(
            rnb_id="BDGSADSSONE1", ads=many_bdg_ads, operation="build"
        )
        BuildingADS.objects.create(
            rnb_id="BDGSADSSTWO2", ads=many_bdg_ads, operation="demolish"
        )

        # User, Org & Token
        self.user = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe"
        )
        org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
        org.users.add(self.user)
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        # Add John to a group and add all permissions on ADS to this group
        group, created = Group.objects.get_or_create(name=ADS_GROUP_NAME)
        self.user.groups.add(group)
        self.user.save()
        content_type = ContentType.objects.get_for_model(ADS)
        permissions = Permission.objects.filter(content_type=content_type)
        for permission in permissions:
            group.permissions.add(permission)
        group.save()

        # User, Org & Token for superuser
        self.superuser = User.objects.create_user(
            first_name="Super-John",
            last_name="Doe",
            username="johndoe_superuser",
            is_superuser=True,
        )
        org.users.add(self.superuser)
        self.token_superuser = Token.objects.create(user=self.superuser)


class ADSEnpointsNoAuthTest(APITestCase):
    def setUp(self) -> None:
        grenoble = create_grenoble()

        ADS.objects.create(file_number="ADS-TEST-UPDATE-BDG", decided_at="2025-01-01")

        ADS.objects.create(file_number="ADS-TEST-DELETE", decided_at="2025-01-01")

    def test_ads_root(self):
        r = self.client.get("/api/alpha/ads/")
        self.assertEqual(r.status_code, 401)

    def test_ads_detail(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST-UPDATE-BDG/")
        self.assertEqual(r.status_code, 401)

    def test_ads_cant_delete(self):
        r = self.client.delete("/api/alpha/ads/ADS-TEST-DELETE/")

        self.assertEqual(r.status_code, 401)
