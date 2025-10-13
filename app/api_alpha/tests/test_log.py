from unittest import mock

from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog


class LogEndpointsTest(APITestCase):
    def test_list_log(self):
        r = self.client.get("/api/alpha/buildings/")

        self.assertEqual(r.status_code, 200)

        count = APIRequestLog.objects.all().count()

        self.assertEqual(count, 1)

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
