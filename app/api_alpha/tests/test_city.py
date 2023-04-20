from rest_framework.test import APITestCase


class BuildingsEnpointsTest(APITestCase):
    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)
