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

    def test_read_one_ads(self):
        r = self.client.get("/api/alpha/ads/ADS-TEST/")
        self.assertEqual(r.status_code, 200)

        r_data = r.json()
        expected = {
            "issue_number": "ADS-TEST",
            "issue_date": "2019-01-01",
            "buildings_operations": [{"operation": "build", "building": "BDG-RNB-ID"}],
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
        r = self.client.post("/api/alpha/ads/", data=data)

        r_data = r.json()
        print("---- response ---")
        print(r_data)
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
        self.assertDictEqual(r_data, expected)
        self.assertEqual(r.status_code, 200)

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

        # ############
        # BuildingADS
        BuildingADS.objects.create(building=b, ads=ads, operation="build")
