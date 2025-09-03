import json

from rest_framework.test import APITestCase
from django.contrib.gis.geos import GEOSGeometry

from batid.models import Building


class SingleBuildingTest(APITestCase):

    def setUp(self):

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

        b = Building.objects.create(
            rnb_id="1234ABCD5678",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            ext_ids=[
                {
                    "source": "bdnb",
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                    "source_version": "25",
                }
            ],
        )

    def test_single_bdg(self):

        r = self.client.get("/api/alpha/buildings/1234ABCD5678/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["rnb_id"], "1234ABCD5678")

    def test_single_bdg_geojson(self):

        r = self.client.get("/api/alpha/buildings/1234ABCD5678/?format=geojson")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["type"], "Feature")
        self.assertEqual(r.data["properties"]["rnb_id"], "1234ABCD5678")
        self.assertEqual(r.data["properties"]["status"], "constructed")
        self.assertListEqual(
            r.data["properties"]["ext_ids"],
            [
                {
                    "source": "bdnb",
                    "source_version": "25",
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                }
            ],
        )

    # test if BuildingGeoJSONSerializer.Meta.fields contains all the fields of BuildingSerializer (except shape and point)
