import json
from unittest import mock

from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from api_alpha.serializers.serializers import ListBuildingQuerySerializer
from batid.models import Building


class LogEndpointsTest(APITestCase):
    def setUp(self):

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

        Building.objects.create(
            rnb_id="1234ABCD5678",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
        )

    @mock.patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
    def test_list_log(self):
        r = self.client.get("/api/alpha/buildings/")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

    @mock.patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
    def test_list_no_log(self):
        r = self.client.get("/api/alpha/buildings/?from=monitoring")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 0)

    @mock.patch("batid.services.geocoders.requests.get")
    def test_guess_log(self, requests_mock):
        requests_mock.return_value.status_code = 200
        requests_mock.return_value.json.return_value = {"features": []}
        r = self.client.get("/api/alpha/buildings/guess/?address=whatever")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

        # BAN API and OSM API
        self.assertEqual(requests_mock.call_count, 2)

    @mock.patch("batid.services.geocoders.requests.get")
    def test_guess_no_log(self, requests_mock):
        requests_mock.return_value.status_code = 200
        requests_mock.return_value.json.return_value = {"features": []}
        r = self.client.get(
            "/api/alpha/buildings/guess/?address=whatever&from=monitoring"
        )

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 0)

        # BAN API and OSM API
        self.assertEqual(requests_mock.call_count, 2)

    def test_ogc_root(self):
        r = self.client.get("/api/alpha/ogc/")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

    def test_ogc_conformance(self):
        r = self.client.get("/api/alpha/ogc/conformance")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

    def test_ogc_buildings_collections(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

    def test_ogc_buildings_items(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings/items")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

    def test_ogc_buildings_item(self):
        r = self.client.get("/api/alpha/ogc/collections/buildings/items/1234ABCD5678")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)
