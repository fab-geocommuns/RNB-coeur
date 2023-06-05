import datetime
import json

from django.test import TestCase
from batid.models import Building, BuildingStatus
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings
from batid.services.bdg_search import BuildingSearch
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel

# Create your tests here.


class SearchTestCase(TestCase):
    def _bdg_in_bbox(self):
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

        b = Building.objects.create(
            rnb_id="IN-BBOX", source="dummy", shape=geom, point=geom.point_on_surface
        )

        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

        return b

    def _bdg_out_bbox(self):
        coords = {
            "coordinates": [
                [
                    [
                        [1.067513184298491, 46.6329053077736],
                        [1.0675308598415256, 46.63278393496779],
                        [1.0674395362045743, 46.632484547548984],
                        [1.0674689954418, 46.632478478867824],
                        [1.0674542658231871, 46.63243599808189],
                        [1.0678166144473664, 46.63238137987915],
                        [1.0679521269400993, 46.63285473580447],
                        [1.067513184298491, 46.6329053077736],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }

        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        b = Building.objects.create(
            rnb_id="OUT-BBOX", source="dummy", shape=geom, point=geom.point_on_surface
        )
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

        return b

    def _bdg_constructed(self):
        coords = {
            "coordinates": [
                [
                    [2.6000591402070654, 48.814763140563656],
                    [2.599867663762808, 48.814565787565414],
                    [2.600525343722012, 48.8144177723068],
                    [2.600708495117374, 48.81477684560585],
                    [2.600367167550303, 48.81493074787656],
                    [2.6000591402070654, 48.814763140563656],
                ]
            ],
            "type": "MultiPolygon",
        }

        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        b = Building.objects.create(
            rnb_id="BDG-CONSTR", source="dummy", shape=geom, point=geom.point_on_surface
        )

        BuildingStatus.objects.create(
            building=b,
            type="constructed",
            is_current=True,
            happened_at=datetime.datetime(2019, 1, 1),
        )

        return b

    def _bdg_demolished(self):
        coords = {
            "coordinates": [
                [
                    [2.6000591402070654, 48.814763140563656],
                    [2.599867663762808, 48.814565787565414],
                    [2.600525343722012, 48.8144177723068],
                    [2.600708495117374, 48.81477684560585],
                    [2.600367167550303, 48.81493074787656],
                    [2.6000591402070654, 48.814763140563656],
                ]
            ],
            "type": "MultiPolygon",
        }

        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        b = Building.objects.create(
            rnb_id="OUT-DEMO", source="dummy", shape=geom, point=geom.point_on_surface
        )

        BuildingStatus.objects.create(
            building=b,
            type="constructed",
            is_current=False,
            happened_at=datetime.datetime(2001, 1, 1),
        )

        BuildingStatus.objects.create(
            building=b,
            type="demolished",
            is_current=True,
            happened_at=datetime.datetime(2021, 1, 1),
        )

        return b

    def _bdg_construction_project(self):
        coords = {
            "coordinates": [
                [
                    [2.6000591402070654, 48.814763140563656],
                    [2.599867663762808, 48.814565787565414],
                    [2.600525343722012, 48.8144177723068],
                    [2.600708495117374, 48.81477684560585],
                    [2.600367167550303, 48.81493074787656],
                    [2.6000591402070654, 48.814763140563656],
                ]
            ],
            "type": "MultiPolygon",
        }

        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        b = Building.objects.create(
            rnb_id="BDG-PROJ", source="dummy", shape=geom, point=geom.point_on_surface
        )

        BuildingStatus.objects.create(
            building=b,
            type="constructionProject",
            is_current=True,
            happened_at=datetime.datetime(2001, 1, 1),
        )

        return b

    def setUp(self):
        ## Test bounding box params
        self._bdg_in_bbox()
        self._bdg_out_bbox()

        ## Test current_status params
        self._bdg_constructed()
        self._bdg_demolished()

        ## Test constructionProject & canceledConstructionProject are protected
        self._bdg_construction_project()

    def test_status_search(self):
        params = {
            "status": "constructed",
        }
        s = BuildingSearch()
        s.set_params(**params)
        qs = s.get_queryset()

        self.assertEqual(qs.count(), 3)

        rnb_id = qs.first().rnb_id
        self.assertEqual(rnb_id, "BDG-CONSTR")

    def test_bdg_default_count(self):
        s = BuildingSearch()
        s.set_params(**{})
        qs = s.get_queryset()
        self.assertEqual(qs.count(), 5)

    def test_bdg_all_status_count(self):
        s = BuildingSearch()

        s.set_params(
            **{
                "status": ",".join(BuildingStatusModel.PUBLIC_TYPES_KEYS),
            }
        )
        qs = s.get_queryset()

        self.assertEqual(qs.count(), 4)

    def test_search(self):
        params = {
            "bb": "46.63505754305547,1.063091817650701,46.63316977636086,1.0677381191425752",
        }

        s = BuildingSearch()
        s.set_params(**params)
        qs = s.get_queryset()

        self.assertEqual(qs.count(), 1)

        rnb_id = qs.first().rnb_id
        self.assertEqual(rnb_id, "IN-BBOX")
