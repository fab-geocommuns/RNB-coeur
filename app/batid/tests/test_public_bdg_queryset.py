import datetime
import json

from django.test import TestCase

from batid.list_bdg import list_bdgs
from batid.models import Building, BuildingStatus
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.tests.helpers import create_bdg, create_grenoble, create_paris


class SearchStatusTestCase(TestCase):
    def setUp(self) -> None:
        self._bdg_constructed()
        self._bdg_demolished()
        self._bdg_construction_project()

    def test_status_search(self):
        params = {
            "status": "constructed",
        }

        qs = list_bdgs(params)

        self.assertEqual(len(qs), 1)

        rnb_id = qs[0].rnb_id
        self.assertEqual(rnb_id, "BDG-CONSTR")

    def test_bdg_all_status_count(self):
        params = {
            "status": ",".join(BuildingStatusModel.PUBLIC_TYPES_KEYS),
        }

        qs = list_bdgs(params)

        self.assertEqual(len(list(qs)), 2)

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

        b = Building.objects.create(
            rnb_id="BDG-CONSTR", shape=geom, point=geom.point_on_surface
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

        b = Building.objects.create(
            rnb_id="OUT-DEMO", shape=geom, point=geom.point_on_surface
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

        b = Building.objects.create(
            rnb_id="BDG-PROJ", shape=geom, point=geom.point_on_surface
        )

        BuildingStatus.objects.create(
            building=b,
            type="constructionProject",
            is_current=True,
            happened_at=datetime.datetime(2001, 1, 1),
        )

        return b


class SearchBBoxTestCase(TestCase):
    def setUp(self) -> None:
        self._bdg_in_bbox()
        self._bdg_out_bbox()

    def test_bbox_filter(self):
        params = {
            "bb": "46.63505754305547,1.063091817650701,46.63316977636086,1.0677381191425752",
        }

        qs = list_bdgs(params)

        self.assertEqual(len(list(qs)), 1)

        rnb_id = qs[0].rnb_id
        self.assertEqual(rnb_id, "IN-BBOX")

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
        b = Building.objects.create(
            rnb_id="IN-BBOX",
            shape=geom,
            point=geom.point_on_surface,
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
        b = Building.objects.create(
            rnb_id="OUT-BBOX",
            shape=geom,
            point=geom.point_on_surface,
        )
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

        return b


class SearchCityTestCase(TestCase):
    def setUp(self) -> None:
        create_grenoble()
        create_paris()

        # Grenoble 1
        coords = [
            [5.727677616548021, 45.18650547532101],
            [5.726661353775256, 45.18614386549888],
            [5.726875130733703, 45.18586106647285],
            [5.727891393506468, 45.18620181594525],
            [5.727677616548021, 45.18650547532101],
        ]
        b = create_bdg("GRENOBLE-1", coords)
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

        # Grenoble 2
        coords = [
            [5.727677616548021, 45.18650547532101],
            [5.726661353775256, 45.18614386549888],
            [5.726875130733703, 45.18586106647285],
            [5.727891393506468, 45.18620181594525],
            [5.727677616548021, 45.18650547532101],
        ]
        b = create_bdg("GRENOBLE-2", coords)
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

        # Paris, to be sure it is not returned
        coords = [
            [2.3523348950355967, 48.8571274784089],
            [2.3516700473636547, 48.85592928853123],
            [2.352705860766207, 48.855707398369816],
            [2.3533851616483332, 48.85690559355845],
            [2.3523348950355967, 48.8571274784089],
        ]
        b = create_bdg("PARIS-1", coords)
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

    def test_grenoble(self):
        qs = list_bdgs({"insee_code": "38185"})

        self.assertEqual(len(list(qs)), 2)
