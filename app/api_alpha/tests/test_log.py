import json
from unittest import mock

from api_alpha.serializers.serializers import ListBuildingQuerySerializer
from batid.models import Building
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog


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

        logs = APIRequestLog.objects.all()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        # assert the response is not logged
        self.assertEqual(log.response, None)

    @mock.patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
    def test_log_big_user_agent(self):
        user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/22G100 [FBAN/FBIOS;FBAV/540.0.0.44.68;FBBV/828638047;FBDV/iPhone12,3;FBMD/iPhone;FBSN/iOS;FBSV/18.6.2;FBSS/3;FBID/phone;FBLC/fr_FR;FBOP/5;FBRV/834137514;IABMV/1]"
        r = self.client.get("/api/alpha/buildings/", HTTP_USER_AGENT=user_agent)

        self.assertEqual(r.status_code, 200)

        logs = APIRequestLog.objects.all()
        self.assertEqual(len(logs), 1)
        log = logs[0]

        # assert the user agent is truncated
        self.assertEqual(log.user_agent, user_agent[:255])

    @mock.patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
    def test_list_no_log(self):
        r = self.client.get("/api/alpha/buildings/?from=monitoring")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 0)

    def test_patch_body_not_logged(self):
        """
        Unauthenticated PATCH on a building, JSON body with a marker, no URL params.
        Expected: the refused call is logged, data is None, query_params is "{}"
        and the marker appears nowhere in the log row.
        """
        r = self.client.patch(
            "/api/alpha/buildings/1234ABCD5678/",
            {"comment": "body-marker"},
            format="json",
        )

        self.assertIn(r.status_code, (401, 403))

        log = APIRequestLog.objects.get()
        self.assertIsNone(log.data)
        self.assertEqual(log.query_params, "{}")
        self.assertNotIn("body-marker", log.query_params)

    def test_post_body_not_logged_url_params_kept(self):
        """
        Unauthenticated POST on /buildings/?from_test=1 with a JSON body holding a marker.
        Expected: query_params holds the URL param from_test, not the body marker; data is None.
        """
        self.client.post(
            "/api/alpha/buildings/?from_test=1",
            {"comment": "body-marker"},
            format="json",
        )

        log = APIRequestLog.objects.get()
        self.assertIsNone(log.data)
        self.assertIn("from_test", log.query_params)
        self.assertNotIn("body-marker", log.query_params)

    @mock.patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
    def test_get_url_params_logged_token_masked(self):
        """
        GET /buildings/?status=constructed&token=secret.
        Expected: query_params holds status=constructed, token is masked and secret is absent.
        """
        r = self.client.get("/api/alpha/buildings/?status=constructed&token=secret")

        self.assertEqual(r.status_code, 200)

        log = APIRequestLog.objects.get()
        self.assertIn("status", log.query_params)
        self.assertIn("constructed", log.query_params)
        self.assertIn("********************", log.query_params)
        self.assertNotIn("secret", log.query_params)

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
