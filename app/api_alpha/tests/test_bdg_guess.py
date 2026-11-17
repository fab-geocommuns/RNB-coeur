from rest_framework.test import APITestCase


class TestSunset(APITestCase):
    def test_gone(self):
        """
        Input: GET /api/alpha/buildings/guess/ with a point.
        Expected: 410 with the end-of-service message.
        """
        r = self.client.get(
            "/api/alpha/buildings/guess/?point=45.184327114924656,5.721176133001023"
        )

        self.assertEqual(r.status_code, 410)
        self.assertEqual(
            r.json(),
            {
                "errors": "Cet endpoint n'est plus disponible. Veuillez utiliser nos autres endpoints pour identifier des bâtiments grâce à un point ou une adresse."
            },
        )
