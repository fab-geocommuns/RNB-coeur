import datetime
import json

from django.test import TestCase
from batid.models import Building, BuildingStatus
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings
from batid.services.search_bdg import BuildingSearch
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
        s = BuildingSearch()
        s.set_params_from_url(**params)
        qs = s.get_queryset()

        self.assertEqual(len(list(qs)), 1)

        rnb_id = qs[0].rnb_id
        self.assertEqual(rnb_id, "BDG-CONSTR")

    def test_bdg_all_status_count(self):
        s = BuildingSearch()

        s.set_params_from_url(
            **{
                "status": ",".join(BuildingStatusModel.PUBLIC_TYPES_KEYS),
            }
        )
        qs = s.get_queryset()

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


class SearchBBoxTestCase(TestCase):
    def setUp(self) -> None:
        self._bdg_in_bbox()
        self._bdg_out_bbox()

    def test_bbox_filter(self):
        params = {
            "bb": "46.63505754305547,1.063091817650701,46.63316977636086,1.0677381191425752",
        }

        s = BuildingSearch()
        s.set_params_from_url(**params)
        qs = s.get_queryset()

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


class SearchPolygonTestCase(TestCase):
    def _bdgs_for_polygon_search(self):
        # Building One
        coords = [
            [-1.1983397171689774, 48.355340684903325],
            [-1.1983895230302721, 48.355231052836956],
            [-1.1983106637508456, 48.355216573112045],
            [-1.1983148142389553, 48.35520209338344],
            [-1.1982618955111946, 48.35519175071778],
            [-1.1982183153827464, 48.35528483463503],
            [-1.198265008377632, 48.3552924192426],
            [-1.1982525569119957, 48.35532620520999],
            [-1.1983397171689774, 48.355340684903325],
        ]
        b = create_bdg("BDG-ONE", coords)
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

        # Building Two
        coords = [
            [-1.198285760819516, 48.3554475587039],
            [-1.1983386795472768, 48.355339305885195],
            [-1.198157095677459, 48.35531034649364],
            [-1.1981487947012397, 48.35533241079355],
            [-1.1981913372067083, 48.355342753430676],
            [-1.1981612461655686, 48.35542135740579],
            [-1.198285760819516, 48.3554475587039],
        ]
        b = create_bdg("BDG-TWO", coords)
        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

    def test_poly_exact_shape(self):
        coords = [
            [-1.1983397171689774, 48.355340684903325],
            [-1.1983895230302721, 48.355231052836956],
            [-1.1983106637508456, 48.355216573112045],
            [-1.1983148142389553, 48.35520209338344],
            [-1.1982618955111946, 48.35519175071778],
            [-1.1982183153827464, 48.35528483463503],
            [-1.198265008377632, 48.3552924192426],
            [-1.1982525569119957, 48.35532620520999],
            [-1.1983397171689774, 48.355340684903325],
        ]

        search = BuildingSearch()
        search.set_params(
            **{
                "poly": GEOSGeometry(
                    json.dumps({"type": "Polygon", "coordinates": [coords]}), srid=4326
                ),
            }
        )

        qs = search.get_queryset()

        self.assertEqual(len(list(qs)), 1)

        rnb_id = qs[0].rnb_id
        self.assertEqual(rnb_id, "BDG-ONE")

    def test_too_big_poly(self):
        coords = [
            [-1.198300287528582, 48.35550202978007],
            [-1.198601197941258, 48.355369644278056],
            [-1.1981612461655686, 48.35516141221896],
            [-1.1979568346091867, 48.35531310453146],
            [-1.197899765382573, 48.355505477318815],
            [-1.198300287528582, 48.35550202978007],
        ]

        search = BuildingSearch()
        search.set_params(
            **{
                "poly": GEOSGeometry(
                    json.dumps({"type": "Polygon", "coordinates": [coords]}), srid=4326
                ),
            }
        )

        qs = search.get_queryset()

        self.assertEqual(len(list(qs)), 0)

    def test_quasi_similar_poly(self):
        coords = [
            [-1.1983369837494706, 48.35533870250637],
            [-1.1983950034402255, 48.3552195335989],
            [-1.1982620856030053, 48.35519219481043],
            [-1.1982009012018864, 48.355314868747485],
            [-1.1983369837494706, 48.35533870250637],
        ]

        search = BuildingSearch()
        search.set_params(
            **{
                "poly": GEOSGeometry(
                    json.dumps({"type": "Polygon", "coordinates": [coords]}), srid=4326
                ),
            }
        )

        qs = search.get_queryset()

        self.assertEqual(len(list(qs)), 1)

    def setUp(self):
        ## Test Polygon search
        self._bdgs_for_polygon_search()


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
        search = BuildingSearch()
        search.set_params(**{"insee_code": "38185"})
        qs = search.get_queryset()
        self.assertEqual(len(list(qs)), 2)
