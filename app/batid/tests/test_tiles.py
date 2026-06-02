import mapbox_vector_tile
from batid.models import Building
from django.contrib.auth.models import User
from django.test import TestCase


class TestVectorTiles(TestCase):
    def setUp(self):

        user = User.objects.create_user(username="reviewer")

        Building.objects.create(
            rnb_id="BDG-MARKED",
            status="constructed",
            point="POINT (2.6000591402070654 48.814763140563656)",
            is_active=True,
            marked_as_correct_by=[user.pk],
        )
        Building.objects.create(
            rnb_id="BDG-EMPTY",
            status="constructed",
            point="POINT (2.6001591402070654 48.814863140563656)",
            is_active=True,
            marked_as_correct_by=[],
        )
        Building.objects.create(
            rnb_id="BDG-NULL",
            status="constructed",
            point="POINT (2.6002591402070654 48.814963140563656)",
            is_active=True,
            marked_as_correct_by=None,
        )

    def _features_by_rnb_id(self, tile_bytes):
        decoded = mapbox_vector_tile.decode(tile_bytes)
        layer = next(iter(decoded.values()))
        return {f["properties"]["rnb_id"]: f for f in layer["features"]}

    def test_tiles_endpoint(self):
        response = self.client.get("/api/alpha/tiles/8166/5902/16.pbf")
        self.assertEqual(response.status_code, 200)

    def test_tiles_endpoint_zoomin(self):
        response = self.client.get("/api/alpha/tiles/shapes/11/1037/703.pbf")
        self.assertEqual(response.status_code, 204)

    def test_tiles_endpoint_zoomout(self):
        response = self.client.get("/api/alpha/tiles/8166/5902/12.pbf")
        self.assertEqual(response.status_code, 204)

    def test_plot_endpoint(self):
        response = self.client.get("/api/alpha/plots/tiles/8166/5902/16.pbf")
        self.assertEqual(response.status_code, 200)

    def test_plot_endpoint_zoomout(self):
        response = self.client.get("/api/alpha/plots/tiles/8166/5902/12.pbf")
        self.assertEqual(response.status_code, 204)

    def test_report_endpoint(self):
        zoomed_out_response = self.client.get("/api/alpha/reports/tiles/7/5/4.pbf")
        self.assertEqual(zoomed_out_response.status_code, 200)
        zoomed_in_response = self.client.get(
            "/api/alpha/reports/tiles/8166/5902/15.pbf"
        )
        self.assertEqual(zoomed_in_response.status_code, 200)

    def test_tile_is_marked_as_correct_property(self):
        """
        Input: three active constructed buildings (set up in setUp) in tile
        33241/22557/16, one with marked_as_correct_by populated with a real
        user id, one with an empty list, one with NULL.
        Expected: the decoded MVT exposes is_marked_as_correct True only for
        the populated one; empty list and NULL both yield False.
        """
        response = self.client.get("/api/alpha/tiles/33241/22557/16.pbf")
        self.assertEqual(response.status_code, 200)

        features = self._features_by_rnb_id(response.content)
        self.assertEqual(set(features.keys()), {"BDG-MARKED", "BDG-EMPTY", "BDG-NULL"})
        self.assertIs(
            features["BDG-MARKED"]["properties"]["is_marked_as_correct"], True
        )
        self.assertIs(
            features["BDG-EMPTY"]["properties"]["is_marked_as_correct"], False
        )
        self.assertIs(features["BDG-NULL"]["properties"]["is_marked_as_correct"], False)
