from rest_framework.test import APITestCase
from django.urls import reverse


class EndpointsTest(APITestCase):
    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)
