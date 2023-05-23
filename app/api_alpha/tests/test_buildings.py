import json

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APITestCase
from batid.models import Building


class BuildingsEnpointsTest(APITestCase):
    def setUp(self) -> None:
        coords = {
            "coordinates": [
                [
                    [
                        [1.0654705955877262, 46.63423852982024],
                        [1.065454930919401, 46.634105152847496],
                        [1.0656648374661017, 46.63409009413692],
                        [1.0656773692001593, 46.63422131990677],
                        [1.0654705955877262, 46.63423852982024],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        Building.objects.create(
            rnb_id="BDGSRNBBIDID",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )

    def test_buildings_root(self):
        r = self.client.get("/api/alpha/buildings/")
        self.assertEqual(r.status_code, 200)

    def test_bdg_fetch(self):
        r = self.client.get("/api/alpha/buildings/BDGSRNBBIDID/")
        self.assertEqual(r.status_code, 200)

    def test_bdg_fetch_to_clean(self):
        r = self.client.get("/api/alpha/buildings/BDGS-RNBB-IDID/")
        self.assertEqual(r.status_code, 200)
