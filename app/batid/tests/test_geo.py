import json

from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TestCase

from api_alpha.tests.utils import coordinates_almost_equal
from batid.exceptions import BuildingTooLarge
from batid.exceptions import BuildingTooSmall
from batid.exceptions import ImpossibleShapeMerge
from batid.exceptions import InvalidWGS84Geometry
from batid.utils.geo import assert_shape_is_valid
from batid.utils.geo import compute_shape_area
from batid.utils.geo import fix_nested_shells
from batid.utils.geo import merge_contiguous_shapes


class TestGeo(TestCase):
    def test_nested_shells(self):
        # a polygon with nested shells
        geo = GEOSGeometry(
            "MULTIPOLYGON (((-0.2603853911940558 49.28965287729145, -0.2603492357597302 49.289646656653346, -0.2601919722379587 49.28961761705052, -0.2601573249932863 49.28967883386184, -0.2601100142797246 49.289670215456006, -0.2600829132996282 49.289742024849495, -0.2600835372682349 49.28975190479929, -0.2597996280503088 49.28967770237899, -0.2598189113333403 49.289569216168644, -0.2598606633102674 49.28948981328902, -0.2599149529332891 49.28950004264068, -0.259950281006515 49.28944960401875, -0.2599786866280709 49.28939845271888, -0.2600636956020137 49.289415949344345, -0.2601529745653078 49.28926148584007, -0.2602535416034688 49.28928575960524, -0.2602808223260912 49.28930391632477, -0.2604181455197162 49.289387477297794, -0.2605629945867315 49.2893070874089, -0.2606026787915336 49.28934740161674, -0.2604369374270364 49.28944545064519, -0.2604016446979928 49.28943110931731, -0.2603307959006165 49.289572479006665, -0.2603853911940558 49.28965287729145)), ((-0.2600423473011662 49.2895352879472, -0.2601168819564045 49.289561164955025, -0.2601306015839213 49.28958238727533, -0.2601185719608941 49.28960970363805, -0.260099858555504 49.28961830668996, -0.2600667897990501 49.289617400823474, -0.2599983715870132 49.28960125532731, -0.2600423473011662 49.2895352879472)))"
        )

        self.assertEqual(geo.valid, False)
        self.assertIn("Nested shells", geo.valid_reason)

        fixed_geo = fix_nested_shells(geo)

        self.assertEqual(fixed_geo.valid, True)
        self.assertEqual(geo.envelope, fixed_geo.envelope)

    def test_nested_shells_w_holes(self):
        # Extremely rare case of nested shells with some correct representation of holes and one error (one case in 15 departements in BDTOPO

        geo = GEOSGeometry(
            "MULTIPOLYGON (((1.3846409477060964 43.550399945838755, 1.3846299686147474 43.55039438292781, 1.3846177527569588 43.55038880161071, 1.3847161974579834 43.55027597661203, 1.3845451759002743 43.550197838191785, 1.3844326710234491 43.55032665235016, 1.3844147995073364 43.55034618462506, 1.3843534352562559 43.550416365063136, 1.384259393631813 43.550372669010756, 1.3843207326416644 43.55030338817234, 1.3843386294856206 43.550282956369166, 1.3843999936122506 43.55021277594603, 1.3842058032220739 43.55012259317292, 1.384143176878126 43.55019365461559, 1.3841663716563646 43.55020479894351, 1.3841510242415074 43.550222568905184, 1.3841400452315216 43.55021700594538, 1.3840773680767369 43.55028986644346, 1.3840871103281962 43.550295410998736, 1.3840717881779623 43.55031228140603, 1.3839740872706656 43.55026673078715, 1.3839076236014145 43.55034223458537, 1.3841775574316002 43.550466842502146, 1.3842274366806264 43.55040909009751, 1.3842396271940234 43.550415571003036, 1.3843092625001614 43.55044720482665, 1.3843214783403928 43.550452786178724, 1.3842511527343049 43.550533632238704, 1.3844209128105893 43.55061265227785, 1.3845065603600573 43.55051493563431, 1.3845187762338689 43.55052051696442, 1.3845871497435422 43.55055303175048, 1.3846006024055066 43.550558631476974, 1.3845609718710745 43.55060393768088, 1.3845951460251864 43.55062064483919, 1.38458615963965 43.55063221008164, 1.3846789904669332 43.55067498790987, 1.3846662178521572 43.55068919658024, 1.384774899196472 43.55074030948848, 1.3847876970980555 43.5507252012601, 1.384881739701701 43.5507688968657, 1.3849188206443548 43.55072625237045, 1.3849567053042484 43.550743014621304, 1.3849183876016957 43.550785640728314, 1.3850124304037421 43.55082933622254, 1.3849996578371333 43.550843544933656, 1.38520616912473 43.550935709407035, 1.385266422584107 43.55086101233895, 1.3851773772413674 43.55081559156897, 1.3851876003142327 43.55080404467469, 1.38526089635879 43.5508375321821, 1.3853235220218678 43.55076647006249, 1.3854348546991426 43.55081132229247, 1.3855114640239952 43.55072696924499, 1.3852561397030911 43.5506106812998, 1.3852459166784252 43.55062222819896, 1.3851701979638373 43.550586904799445, 1.3851600002225661 43.55059755214558, 1.3850830448209057 43.55056221028696, 1.3850932678676324 43.55055066340365, 1.385016312569865 43.550515321498914, 1.385026535621662 43.550503774622264, 1.3848689656216775 43.5504312363711, 1.3848587678522029 43.55044188368773, 1.3847830496134956 43.55040656002271, 1.3847728265300496 43.55041810687564, 1.3847374156758925 43.550401381371934, 1.3847105579109311 43.550432478949155, 1.3846983673408035 43.55042599809641, 1.3846983420372074 43.55042689764095, 1.3846409477060964 43.550399945838755), (1.384678601212575 43.55046890017025, 1.3846172371527368 43.550539080763485, 1.3845231951266457 43.55049538493583, 1.3845845592547121 43.55042520439791, 1.384678601212575 43.55046890017025), (1.3851036343071477 43.55066600752602, 1.385197677054239 43.55070970285611, 1.3851363133714134 43.550779883754636, 1.3850422705560912 43.55073618836923, 1.3851036343071477 43.55066600752602)), ((1.3847467661890571 43.55059680339142, 1.3848371235306656 43.55063954427612, 1.3848959885834997 43.550570226294525, 1.3848068680787549 43.55052750386381, 1.3847467661890571 43.55059680339142)))"
        )

        self.assertEqual(geo.valid, False)
        self.assertIn("Nested shells", geo.valid_reason)

        fixed_geo = fix_nested_shells(geo)

        self.assertEqual(fixed_geo.valid, True)
        self.assertEqual(geo.envelope, fixed_geo.envelope)

    def test_merge_contiguous_shapes_empty(self):
        shapes = []
        with self.assertRaises(ImpossibleShapeMerge):
            merge_contiguous_shapes(shapes)

    def test_merge_contiguous_shapes_single(self):
        shapes = [GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")]
        merged_shapes = merge_contiguous_shapes(shapes)
        self.assertEqual(merged_shapes, shapes[0])

    def test_merge_contiguous_shapes_multiple(self):
        shape_1 = GEOSGeometry("MULTIPOLYGON (((0 0, 0 1, 1 1, 1 0, 0 0)))")
        shape_2 = GEOSGeometry("POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))")
        shape_3 = GEOSGeometry("POLYGON ((2 0, 2 1, 3 1, 3 0, 2 0))")

        shapes = [shape_1, shape_2, shape_3]

        merged_shapes = merge_contiguous_shapes(shapes)
        res_coordinates = json.loads(merged_shapes.json)["coordinates"]
        expected_coordinates = [
            [
                [0.0, 1.0],
                [3.0, 1.0],
                [3.0, 0.0],
                [0.0, 0.0],
                [0.0, 1.0],
            ]
        ]

        self.assertTrue(
            coordinates_almost_equal.check(res_coordinates, expected_coordinates)
        )

    def test_merge_contiguous_shapes_not_contiguous(self):
        shape_1 = GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        shape_2 = GEOSGeometry("POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))")
        shape_3 = GEOSGeometry("POLYGON ((2 0, 2 1, 3 1, 3 0, 2 0))")

        # not contiguous
        shape_4 = GEOSGeometry("POLYGON ((14 10, 14 11, 15 11, 15 10, 14 10))")

        shapes = [shape_1, shape_2, shape_3, shape_4]

        with self.assertRaises(Exception):
            merge_contiguous_shapes(shapes)

    def test_merge_contiguous_shapes_no_point(self):
        shape_1 = GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        shape_2 = GEOSGeometry("POINT (0.5 0.5)")

        shapes = [shape_1, shape_2]

        with self.assertRaises(Exception) as e:
            merge_contiguous_shapes(shapes)
            self.assertEqual(
                str(e), "Only Polygon and MultiPolygon shapes can be merged"
            )

    def test_two_shapes_with_ponctual_intersection(self):
        # if 2 shapes share only one point, but also almost a vertice, we would like
        # the additional buffer to give us a little flexibility in that case.

        # those 2 shapes almost share the (1 0)---(1 1) vertice
        # but there is only one point of contact : (1 0)
        shape_1 = GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        shape_2 = GEOSGeometry("POLYGON ((1 0, 1.00000001 1, 2 1, 2 0, 1 0))")

        shapes = [shape_1, shape_2]

        merged_shape = merge_contiguous_shapes(shapes)
        res_coordinates = json.loads(merged_shape.json)["coordinates"]
        expected_coordinates = [
            [[0.0, 1.0], [2.0, 1.0], [2.0, 0.0], [0.0, 0.0], [0.0, 1.0]]
        ]

        self.assertTrue(
            coordinates_almost_equal.check(res_coordinates, expected_coordinates)
        )

    def test_merge_shapes_almost_contiguous(self):
        # if the shapes are almost contiguous, we would like to add a little flexibility
        # and allow to merge them
        # this test case comes from a real-world interesting scenario:
        # a building is split in 4, the 4 geometry are almost contiguous but do not touch each other
        # Additionally, the resulting merge is not valid and needs to be fixed afterwards using the make_valid() function

        shape_1 = GEOSGeometry(
            "MULTIPOLYGON (((3.399813196293031 47.84852361732513, 3.399785416914514 47.848563312224655, 3.399821611014261 47.848575788937545, 3.399835014986967 47.84858024327614, 3.399911395806362 47.84846932449911, 3.399878399999999 47.84844729999998, 3.399791017237281 47.848388369107376, 3.399813196293031 47.84852361732513)))"
        )
        shape_2 = GEOSGeometry(
            "MULTIPOLYGON (((3.3997421 47.848407499999986, 3.399767427393122 47.84855739367596, 3.399785416914514 47.848563312224655, 3.399813196293031 47.84852361732513, 3.399791017237281 47.848388369107376, 3.399759576696018 47.84836716557327, 3.399739908225637 47.848394388497766, 3.3997421 47.848407499999986)))"
        )
        shape_3 = GEOSGeometry(
            "MULTIPOLYGON (((3.399650040362037 47.84851877326723, 3.399767427393118 47.84855739367596, 3.3997421 47.84840749999999, 3.399739908225635 47.848394388497766, 3.399650040362037 47.84851877326723)))"
        )
        shape_4 = GEOSGeometry(
            "MULTIPOLYGON (((3.399791017237283 47.84838836910738, 3.3998784 47.84844729999998, 3.399911395806356 47.84846932449911, 3.399958016224987 47.84840162295606, 3.399964633540605 47.84839260034244, 3.399917702844714 47.848374760245584, 3.399839264852122 47.84834762205743, 3.399830599999999 47.84834869999998, 3.399785714906284 47.84835603530853, 3.399791017237283 47.84838836910738)))"
        )
        shapes = [shape_1, shape_2, shape_3, shape_4]

        # without the added the flexibility, the function would raise
        merged_shape = merge_contiguous_shapes(shapes)

        # also check the result is valid, because for this specific test case, the resulting merged shape is naturally invalid
        # and is fixed by the make_valid() function
        self.assertTrue(merged_shape.valid)


class TestShapeVerification(TestCase):
    def test_valid_geometry_point(self):
        shape = GEOSGeometry("POINT (25 12)")
        self.assertTrue(assert_shape_is_valid(shape))

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_valid_geometry_polygon(self):
        shape = GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        self.assertTrue(assert_shape_is_valid(shape))

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_valid_geometry_multipolygon(self):
        shape = GEOSGeometry(
            "MULTIPOLYGON (((0 0, 0 1, 1 1, 1 0, 0 0)),((10 0, 10 1, 11 1, 11 0, 10 0)))"
        )
        self.assertTrue(assert_shape_is_valid(shape))

    def test_invalid_geometry(self):
        # a butterfly shape (self intersection)
        shape = GEOSGeometry("POLYGON ((0 0, 1 0, 0 1 , 1 1, 0 0))")

        with self.assertRaises(InvalidWGS84Geometry):
            assert_shape_is_valid(shape)

    def test_invalid_geometry_crs(self):
        shape = GEOSGeometry("POLYGON ((1000 0, 1000 1, 1001 1, 1001 0, 1000 0))")
        with self.assertRaises(InvalidWGS84Geometry):
            assert_shape_is_valid(shape)

    def test_maximum_building_area(self):
        shape = GEOSGeometry(
            "MULTIPOLYGON (((0 0, 0 1, 1 1, 1 0, 0 0)),((10 0, 10 1, 11 1, 11 0, 10 0)))"
        )
        with self.assertRaises(BuildingTooLarge):
            assert_shape_is_valid(shape)

    def test_minimum_building_area(self):
        # This is a real 3,7m2 building shape
        shape = GEOSGeometry(
            "POLYGON ((7.677333085258134 48.54452683482581, 7.677351468439592 48.54453512234111, 7.677367445522537 48.544516470391386, 7.677349142548201 48.54450908086052, 7.677333085258134 48.54452683482581))"
        )
        with self.assertRaises(BuildingTooSmall):
            assert_shape_is_valid(shape)

    def test_shape_area_compute(self):

        shape = GEOSGeometry(
            "POLYGON ((7.677333085258134 48.54452683482581, 7.677351468439592 48.54453512234111, 7.677367445522537 48.544516470391386, 7.677349142548201 48.54450908086052, 7.677333085258134 48.54452683482581))"
        )
        area = compute_shape_area(shape)

        rounded_area = round(area, 4)

        self.assertEqual(rounded_area, 3.7724)
