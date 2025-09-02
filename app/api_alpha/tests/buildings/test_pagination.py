from rest_framework.test import APITestCase

from batid.tests.helpers import create_default_bdg
from batid.tests.helpers import create_grenoble


class EndpointTest(APITestCase):
    def setUp(self):

        create_grenoble()

        # Create X buildings
        for i in range(200):

            rnb_id = str(i).zfill(12)
            create_default_bdg(rnb_id)

    def test_first_page(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertIn(
            "http://testserver/api/alpha/buildings/?cursor=",
            data["next"],
        )
        self.assertEqual(data["previous"], None)

        self.assertEqual(len(data["results"]), 20)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000000")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000005")
        self.assertEqual(data["results"][16]["rnb_id"], "000000000016")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000019")

    def test_params_conservation(self):

        r = self.client.get("/api/alpha/buildings/?insee_code=38185")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertIn(
            "insee_code=38185",
            data["next"],
        )
