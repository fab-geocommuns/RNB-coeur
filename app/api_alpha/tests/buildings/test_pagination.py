from unittest.mock import patch

from api_alpha.serializers.serializers import ListBuildingQuerySerializer
from batid.models import Address, Building
from batid.tests.helpers import (
    coords_to_mp_geom,
    create_default_bdg,
    create_grenoble,
    internal_ids,
)
from rest_framework.test import APITestCase


class EndpointTest(APITestCase):
    def setUp(self):

        create_grenoble()

        # Create X buildings
        for i in range(200):

            rnb_id = str(i).zfill(12)
            create_default_bdg(rnb_id)

    @patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
    def test_first_page(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        next_page = data["next"]

        self.assertIsNone(data["previous"])

        self.assertEqual(len(data["results"]), 20)

        # Since the data as no expliciti ORDER BY we want to check the results have a consistent order
        self.assertEqual(data["results"][0]["rnb_id"], "000000000000")
        self.assertEqual(data["results"][4]["rnb_id"], "000000000004")

        r = self.client.get(next_page)
        data = r.json()
        self.assertEqual(len(data["results"]), 20)
        self.assertEqual(data["results"][0]["rnb_id"], "000000000020")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000039")

        next_page = data["next"]

        r = self.client.get(next_page)
        data = r.json()
        self.assertEqual(len(data["results"]), 20)
        self.assertEqual(data["results"][0]["rnb_id"], "000000000040")

        # test the previous page link send you properly back in the results
        previous_page = data["previous"]
        r = self.client.get(previous_page)
        data = r.json()
        self.assertEqual(len(data["results"]), 20)
        self.assertEqual(data["results"][0]["rnb_id"], "000000000020")
        self.assertEqual(data["results"][19]["rnb_id"], "000000000039")

    @patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
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

    @patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
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

    @patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
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

    @patch.object(ListBuildingQuerySerializer, "validate", lambda self, data: data)
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
        self.assertEqual(data["features"][0]["id"], "000000000020")
        self.assertEqual(data["features"][5]["id"], "000000000025")
        self.assertEqual(data["features"][16]["id"], "000000000036")
        self.assertEqual(data["features"][19]["id"], "000000000039")

    def test_params_conservation(self):

        r = self.client.get("/api/alpha/buildings/?insee_code=38185")
        self.assertEqual(r.status_code, 200)

        data = r.json()

        self.assertIn(
            "insee_code=38185",
            data["next"],
        )


class AddressJoinPaginationTest(APITestCase):
    """
    Pagination of listings filtered on a BAN interop key. This filter joins the
    building <> address link table, which also has an "id" column.
    """

    CLE_INTEROP = "38185_1234_00001"

    def setUp(self):
        Address.objects.create(cle_interop=self.CLE_INTEROP)
        geom = coords_to_mp_geom(
            [
                [5.717918517856731, 45.178820091145724],
                [5.718008279271032, 45.17865980057857],
                [5.7184092135875915, 45.17866401875747],
                [5.717918517856731, 45.178820091145724],
            ]
        )
        # 7 buildings sharing the same address: 2 pages of 5 buildings
        self.rnb_ids = []
        for i in range(7):
            bdg = Building.objects.create(
                rnb_id=f"ADDRPAGE{i:04d}",
                shape=geom,
                point=geom.point_on_surface,
                status="constructed",
                event_type="creation",
                addresses_internal_id=internal_ids([self.CLE_INTEROP]),
            )
            self.rnb_ids.append(bdg.rnb_id)

    @staticmethod
    def _link(data, rel):
        # GeoJSON responses put their pagination links in "links", JSON ones in
        # "next" / "previous"
        if "links" in data:
            return next(
                (link["href"] for link in data["links"] if link["rel"] == rel), None
            )
        return data["previous" if rel == "prev" else rel]

    @staticmethod
    def _ids(data):
        if "features" in data:
            return [f["id"] for f in data["features"]]
        return [b["rnb_id"] for b in data["results"]]

    def _assert_pages(self, first_url):
        r = self.client.get(first_url)
        self.assertEqual(r.status_code, 200)
        page_1 = r.json()
        self.assertEqual(self._ids(page_1), self.rnb_ids[:5])

        r = self.client.get(self._link(page_1, "next"))
        self.assertEqual(r.status_code, 200)
        page_2 = r.json()
        self.assertEqual(self._ids(page_2), self.rnb_ids[5:])
        self.assertIsNone(self._link(page_2, "next"))

        r = self.client.get(self._link(page_2, "prev"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._ids(r.json()), self.rnb_ids[:5])

    def test_buildings_json(self):
        """
        Input: GET /buildings/?cle_interop_ban=<key of 7 buildings>&limit=5, then
        the "next" link, then the "previous" link of page 2.
        Expected: 200 on every page (page 2 used to be a 500, "column reference
        "id" is ambiguous"): buildings 1-5, then 6-7 without a next link, then
        1-5 again.
        """
        self._assert_pages(
            f"/api/alpha/buildings/?cle_interop_ban={self.CLE_INTEROP}&limit=5"
        )

    def test_buildings_geojson(self):
        """
        Input: same as test_buildings_json, with format=geojson.
        Expected: 200 on every page, with the same buildings in each page.
        """
        self._assert_pages(
            f"/api/alpha/buildings/?cle_interop_ban={self.CLE_INTEROP}&limit=5"
            "&format=geojson"
        )

    def test_ogc_items(self):
        """
        Input: GET /ogc/collections/buildings/items?cle_interop_ban=<key of 7
        buildings>&limit=5, then the "next" link, then the "prev" link of page 2.
        Expected: 200 on every page, with the same buildings in each page as on
        /buildings/.
        """
        self._assert_pages(
            "/api/alpha/ogc/collections/buildings/items"
            f"?cle_interop_ban={self.CLE_INTEROP}&limit=5"
        )
