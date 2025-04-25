from batid.models import Building
from rest_framework.test import APITestCase

from batid.tests.helpers import create_default_bdg
from batid.tests.helpers import create_grenoble


class EndpointTest(APITestCase):
    def setUp(self):

        Building.objects.all().delete()
        create_grenoble()

        # Create X buildings
        for i in range(200):

            rnb_id = str(i).zfill(12)
            create_default_bdg(rnb_id)

    def test_first_page(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertIsNone(data["previous"])

        self.assertEqual(len(data["results"]), 20)
        self.assertEqual(data["results"][0]["rnb_id"], "000000000000")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000005")
        self.assertEqual(data["results"][16]["rnb_id"], "000000000016")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000019")

    def test_nth_page(self):

        # Go to page 5
        page_url = "/api/alpha/buildings/"
        for i in range(5):
            r = self.client.get(page_url)
            self.assertEqual(r.status_code, 200)
            data = r.json()
            page_url = data["next"]

        self.assertEqual(len(data["results"]), 20)

        self.assertEqual(data["results"][0]["rnb_id"], "000000000080")
        self.assertEqual(data["results"][5]["rnb_id"], "000000000085")
        self.assertEqual(data["results"][16]["rnb_id"], "000000000096")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000099")
        self.assertEqual(r.status_code, 200)

    def test_params_conservation(self):

        # Go to page 3
        page_url = "/api/alpha/buildings/?insee_code=38185"
        for _ in range(5):
            r = self.client.get(page_url)
            data = r.json()
            page_url = data["next"]

        self.assertEqual(r.status_code, 200)

        self.assertIn("insee_code=38185", data["next"])
        self.assertIn("insee_code=38185", data["previous"])
