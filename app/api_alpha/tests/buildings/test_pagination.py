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
        r = self.client.get("/api/alpha/buildings/?limit=5")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        next_page = data["next"]

        self.assertIsNone(data["previous"])

        self.assertEqual(len(data["results"]), 5)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000000")
        self.assertEqual(data["results"][4]["rnb_id"], "000000000004")

        r = self.client.get(next_page)
        data = r.json()
        self.assertEqual(len(data["results"]), 5)
        self.assertEqual(data["results"][0]["rnb_id"], "000000000005")
        self.assertEqual(data["results"][4]["rnb_id"], "000000000009")

        next_page = data["next"]

        r = self.client.get(next_page)
        data = r.json()
        self.assertEqual(len(data["results"]), 5)
        self.assertEqual(data["results"][0]["rnb_id"], "000000000010")
        self.assertEqual(data["results"][4]["rnb_id"], "000000000014")

    def test_limit_param(self):
        r = self.client.get("/api/alpha/buildings/?limit=10")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertIsNone(data["previous"])

        self.assertEqual(len(data["results"]), 10)

        # Since the data as no explicit ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000000")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000005")
        self.assertEqual(data["results"][8]["rnb_id"], "000000000008")
        self.assertEqual(data["results"][9]["rnb_id"], "000000000009")

    def test_first_page_geojson(self):

        r = self.client.get("/api/alpha/buildings/?format=geojson")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        # Assert there is a next link
        links_rels = [link["rel"] for link in data["links"]]
        self.assertIn("next", links_rels)
        self.assertNotIn("prev", links_rels)

        for link in data["links"]:
            if link["rel"] == "next":
                self.assertIsNotNone(link["href"])

        self.assertEqual(len(data["features"]), 20)

        # Since the data as no explicit ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["features"][0]["id"], "000000000000")
        self.assertEqual(data["features"][5]["id"], "000000000005")
        self.assertEqual(data["features"][16]["id"], "000000000016")
        self.assertEqual(data["features"][19]["id"], "000000000019")

    def test_next_page(self):

        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        next_url = data["next"]

        r = self.client.get(next_url)
        self.assertEqual(r.status_code, 200)
        data = r.json()

        self.assertEqual(len(data["results"]), 20)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000020")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000025")
        self.assertEqual(data["results"][16]["rnb_id"], "000000000036")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000039")

    def test_next_page_geojson(self):

        r = self.client.get("/api/alpha/buildings/?format=geojson")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        # Assert there is a next link
        links_rels = [link["rel"] for link in data["links"]]
        self.assertIn("next", links_rels)

        for link in data["links"]:
            if link["rel"] == "next":
                next_link = link["href"]

        self.assertEqual(len(data["features"]), 20)

        # follow the next link
        r = self.client.get(next_link)
        data = r.json()
        links_rels = [link["rel"] for link in data["links"]]
        self.assertIn("next", links_rels)
        self.assertIn("prev", links_rels)

        for link in data["links"]:
            if link["rel"] == "next":
                self.assertIsNotNone(link["href"])
            if link["rel"] == "prev":
                self.assertIsNotNone(link["href"])

        # Since the data as no explicit ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["features"][0]["properties"]["rnb_id"], "000000000020")
        self.assertEqual(data["features"][5]["properties"]["rnb_id"], "000000000025")
        self.assertEqual(data["features"][16]["properties"]["rnb_id"], "000000000036")
        self.assertEqual(data["features"][19]["properties"]["rnb_id"], "000000000039")

    def test_params_conservation(self):

        r = self.client.get("/api/alpha/buildings/?insee_code=38185")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertIn(
            "insee_code=38185",
            data["next"],
        )
