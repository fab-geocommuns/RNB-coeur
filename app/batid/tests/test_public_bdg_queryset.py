import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from batid.list_bdg import list_bdgs
from batid.models import Building, Plot
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.tests.helpers import create_bdg
from batid.tests.helpers import create_grenoble
from batid.tests.helpers import create_paris


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
            rnb_id="BDG-CONSTR",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
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
            rnb_id="OUT-DEMO",
            shape=geom,
            point=geom.point_on_surface,
            status="demolished",
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
            rnb_id="BDG-PROJ",
            shape=geom,
            point=geom.point_on_surface,
            status="constructionProject",
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
            status="constructed",
        )

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
            status="constructed",
        )

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
        create_bdg("GRENOBLE-1", coords)

        # Grenoble 2
        coords = [
            [5.727677616548021, 45.18650547532101],
            [5.726661353775256, 45.18614386549888],
            [5.726875130733703, 45.18586106647285],
            [5.727891393506468, 45.18620181594525],
            [5.727677616548021, 45.18650547532101],
        ]
        create_bdg("GRENOBLE-2", coords)

        # Paris, to be sure it is not returned
        coords = [
            [2.3523348950355967, 48.8571274784089],
            [2.3516700473636547, 48.85592928853123],
            [2.352705860766207, 48.855707398369816],
            [2.3533851616483332, 48.85690559355845],
            [2.3523348950355967, 48.8571274784089],
        ]
        create_bdg("PARIS-1", coords)

    def test_grenoble(self):
        qs = list_bdgs({"insee_code": "38185"})

        self.assertEqual(len(list(qs)), 2)


class SearchWithPlots(TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bdg_on_both_plots = None
        self.bdg_minuscule_corner = None
        self.bdg_point = None
        self.bdg_point_on_exact_corner = None

    def setUp(self):

        # The two plots are side by side

        Plot.objects.create(
            id="one",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [
                                    [0.9105774090996306, 44.84936803275076],
                                    [0.9102857535320368, 44.84879419445585],
                                    [0.9104349726604539, 44.84847040607977],
                                    [0.9109969204173751, 44.848225799624316],
                                    [0.9112463293299982, 44.84857273425834],
                                    [0.9113505129542716, 44.84894428770244],
                                    [0.9113883978533295, 44.84920168780678],
                                    [0.9105774090996306, 44.84936803275076],
                                ]
                            ]
                        ],
                        "type": "MultiPolygon",
                    }
                ),
                srid=4326,
            ),
        )

        Plot.objects.create(
            id="two",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [
                                    [0.910571664716457, 44.84936946559145],
                                    [0.9103209027180412, 44.84944151365943],
                                    [0.9100424249191121, 44.84885483391221],
                                    [0.9102799889177788, 44.84879588489878],
                                    [0.910571664716457, 44.84936946559145],
                                ]
                            ]
                        ],
                        "type": "MultiPolygon",
                    }
                ),
                srid=4326,
            ),
        )

        self.bdg_on_both_plots = Building.create_new(
            user=None,
            event_origin={"dummy": "dummy"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [0.9104005886575237, 44.84928501664322],
                                [0.9102901511915604, 44.84910387339187],
                                [0.9105699884996739, 44.84904017453093],
                                [0.910669195036661, 44.84922264503825],
                                [0.9104005886575237, 44.84928501664322],
                            ]
                        ],
                        "type": "Polygon",
                    }
                ),
                srid=4326,
            ),
        )

        self.bdg_minuscule_corner = Building.create_new(
            user=None,
            event_origin={"dummy": "dummy"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [0.9101392761545242, 44.849463423418655],
                                [0.9103279421314028, 44.849432783031574],
                                [0.9103827965568883, 44.84963842685542],
                                [0.9101484185592597, 44.84964255150933],
                                [0.9101392761545242, 44.849463423418655],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        self.bdg_point = Building.create_new(
            user=None,
            event_origin={"dummy": "dummy"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [0.9104898999294733, 44.8489512225878],
                        "type": "Point",
                    }
                )
            ),
        )

        # This building is on the exact corner of one of the plot
        self.bdg_point_on_exact_corner = Building.create_new(
            user=None,
            event_origin={"dummy": "dummy"},
            status="constructed",
            addresses_id=[],
            ext_ids=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [0.9105774090996306, 44.84936803275076],
                        "type": "Point",
                    }
                )
            ),
        )

    def test_bdg_on_both_plots(self):
        qs = list_bdgs({"withPlots": "1"}).filter(rnb_id=self.bdg_on_both_plots.rnb_id)

        # Check there is only one building
        count = qs.count()
        self.assertEqual(count, 1)

        bdg = qs.first()

        bdg_plots_ids = [plot["id"] for plot in bdg.plots]
        self.assertListEqual(["one", "two"], bdg_plots_ids)

        self.assertAlmostEqual(bdg.plots[0]["bdg_cover_ratio"], 0.52, delta=0.01)
        self.assertAlmostEqual(bdg.plots[1]["bdg_cover_ratio"], 0.44, delta=0.01)

    def test_minuscule_intersection(self):
        qs = list_bdgs({"withPlots": "1"}).filter(
            rnb_id=self.bdg_minuscule_corner.rnb_id
        )

        # Check there is only one building
        count = qs.count()
        self.assertEqual(count, 1)

        bdg = qs.first()

        bdg_plots_ids = [plot["id"] for plot in bdg.plots]
        self.assertListEqual(["two"], bdg_plots_ids)
        self.assertAlmostEqual(bdg.plots[0]["bdg_cover_ratio"], 0.0016, delta=0.0001)

    def test_bdg_point(self):
        """
        When checking for building with point the intersecting ratio is always 1

        """

        qs = list_bdgs({"withPlots": "1"}).filter(rnb_id=self.bdg_point.rnb_id)

        # Check there is only one building
        count = qs.count()
        self.assertEqual(count, 1)

        bdg = qs.first()
        bdg_plots_ids = [plot["id"] for plot in bdg.plots]
        self.assertListEqual(["one"], bdg_plots_ids)
        self.assertEqual(bdg.plots[0]["bdg_cover_ratio"], 1.0)

    def test_bdg_point_on_exact_corner(self):

        qs = list_bdgs({"withPlots": "1"}).filter(
            rnb_id=self.bdg_point_on_exact_corner.rnb_id
        )

        # Check there is only one building
        count = qs.count()
        self.assertEqual(count, 1)

        bdg = qs.first()
        bdg_plots_ids = [plot["id"] for plot in bdg.plots]
        self.assertListEqual(["one"], bdg_plots_ids)
        self.assertEqual(bdg.plots[0]["bdg_cover_ratio"], 1.0)
