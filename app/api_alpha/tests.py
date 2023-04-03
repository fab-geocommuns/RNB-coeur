import json

from django.test import TestCase
from batid.models import Building
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings
from batid.logic.search import BuildingSearch

# Create your tests here.

class ApiAlphaTestCase(TestCase):

    def setUp(self):

        ## In search
        coords = {
            "coordinates": [
                [[
                    [
                        1.0654705955877262,
                        46.63423852982024
                    ],
                    [
                        1.065454930919401,
                        46.634105152847496
                    ],
                    [
                        1.0656648374661017,
                        46.63409009413692
                    ],
                    [
                        1.0656773692001593,
                        46.63422131990677
                    ],
                    [
                        1.0654705955877262,
                        46.63423852982024
                    ]
                ]]
            ],
            "type": "MultiPolygon"
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        Building.objects.create(
            rnb_id="IN-SEARCH",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface
        )

        ## Not in search

        coords = {
            "coordinates": [
                [
                    [[
                        1.067513184298491,
                        46.6329053077736
                    ],
                    [
                        1.0675308598415256,
                        46.63278393496779
                    ],
                    [
                        1.0674395362045743,
                        46.632484547548984
                    ],
                    [
                        1.0674689954418,
                        46.632478478867824
                    ],
                    [
                        1.0674542658231871,
                        46.63243599808189
                    ],
                    [
                        1.0678166144473664,
                        46.63238137987915
                    ],
                    [
                        1.0679521269400993,
                        46.63285473580447
                    ],
                    [
                        1.067513184298491,
                        46.6329053077736
                    ]]
                ]
            ],
            "type": "MultiPolygon"
        }

        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        Building.objects.create(
            rnb_id="OUT-SEARCH",
            source="dummy",
            shape=geom,
            point=geom.point_on_surface
        )


    def test_bdg_count(self):

        all_count = Building.objects.all().count()
        self.assertEqual(all_count, 2)

    def test_search(self):

        params = {
            "bb": "46.63505754305547,1.063091817650701,46.63316977636086,1.0677381191425752",
        }

        s = BuildingSearch(**params)
        qs = s.get_queryset()

        self.assertEqual(qs.count(), 1)

        rnb_id = qs.first().rnb_id
        self.assertEqual(rnb_id, "IN-SEARCH")
