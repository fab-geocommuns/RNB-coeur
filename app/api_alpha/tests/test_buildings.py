import json

from batid.models import Building
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase


class BuildingsEnpointsTest(APITestCase):
    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

    def test_one_bdg_with_dash(self):
        r = self.client.get("/api/alpha/buildings/BDG-RNB-ID/")
        self.assertEqual(r.status_code, 200)

    def setUp(self) -> None:
        # ############
        # Building
        coords = {
            "coordinates": [
                [
                    [
                        [5.717918517856731, 45.178820091145724],
                        [5.718008279271032, 45.17865980057857],
                        [5.7184092135875915, 45.17866401875747],
                        [5.7184451181529425, 45.17884961830637],
                        [5.717924501950705, 45.17893819969589],
                        [5.717918517856731, 45.178820091145724],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        # Grenoble
        b = Building.objects.create(
            rnb_id="BDGRNBID",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )
