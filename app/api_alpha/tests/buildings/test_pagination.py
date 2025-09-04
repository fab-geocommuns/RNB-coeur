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

        self.assertEqual(
            data["next"], "http://testserver/api/alpha/buildings/?cursor=2"
        )
        self.assertIsNone(data["previous"])

        self.assertEqual(len(data["results"]), 20)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000000")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000005")
        self.assertEqual(data["results"][16]["rnb_id"], "000000000016")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000019")

    def test_first_page_geojson(self):

        r = self.client.get("/api/alpha/buildings/?format=geojson")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertEqual(
            data["next"],
            "http://testserver/api/alpha/buildings/?cursor=2&format=geojson",
        )
        self.assertIsNone(data["previous"])

        self.assertEqual(len(data["results"]["features"]), 20)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(
            data["results"]["features"][0]["properties"]["rnb_id"], "000000000000"
        )
        self.assertEqual(
            data["results"]["features"][5]["properties"]["rnb_id"], "000000000005"
        )
        self.assertEqual(
            data["results"]["features"][16]["properties"]["rnb_id"], "000000000016"
        )
        self.assertEqual(
            data["results"]["features"][19]["properties"]["rnb_id"], "000000000019"
        )

    def test_nth_page(self):

        r = self.client.get("/api/alpha/buildings/?cursor=5")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertEqual(
            data["next"], "http://testserver/api/alpha/buildings/?cursor=6"
        )
        self.assertEqual(
            data["previous"], "http://testserver/api/alpha/buildings/?cursor=4"
        )

        self.assertEqual(len(data["results"]), 20)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000080")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000085")
        self.assertEqual(data["results"][16]["rnb_id"], "000000000096")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000099")
        self.assertEqual(r.status_code, 200)

    def test_params_conservation(self):

        r = self.client.get("/api/alpha/buildings/?insee_code=38185&cursor=3")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertEqual(
            data["next"],
            "http://testserver/api/alpha/buildings/?cursor=4&insee_code=38185",
        )

        self.assertEqual(
            data["previous"],
            "http://testserver/api/alpha/buildings/?cursor=2&insee_code=38185",
        )
