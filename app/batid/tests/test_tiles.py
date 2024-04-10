from django.test import TestCase

from batid.models import Building


class TestVectorTiles(TestCase):
    def test_tiles_endpoint(self):
        Building.objects.create(
            rnb_id="BDG-1",
            status="constructed",
            point="POINT (2.6000591402070654 48.814763140563656)",
            is_active=True,
        )

        Building.objects.create(
            rnb_id="BDG-2",
            status="constructed",
            point="POINT (2.6010591402070654 48.815763140563656)",
            is_active=False,
        )

        response = self.client.get("/api/alpha/tiles/8166/5902/14.pbf")
        self.assertEqual(response.status_code, 200)
