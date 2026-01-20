import csv
import json
import os
from io import StringIO
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TransactionTestCase
from requests import Response

from batid.models import Address
from batid.models import Building
from batid.services.guess_bdg_new import ClosestFromPointHandler
from batid.services.guess_bdg_new import GeocodeAddressHandler
from batid.services.guess_bdg_new import GeocodeNameHandler
from batid.services.guess_bdg_new import Guesser
from batid.services.guess_bdg_new import PartialRoofHandler
from batid.tests.helpers import create_default_bdg
from batid.tests.helpers import create_from_geojson


class TestGuesser(TransactionTestCase):
    WORK_FILE = "batid/fixtures/guesser_test_file.json"

    def setUp(self):
        self._create_rnb_bdgs()
        self._create_guess_work_file()

    def tearDown(self):
        if os.path.exists(self.WORK_FILE):
            os.remove(self.WORK_FILE)

    def _create_rnb_bdgs(self):
        rnb_bdgs = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"rnb_id": "BigLong"},
                    "geometry": {
                        "coordinates": [
                            [
                                [-0.5628922920153343, 44.82595445471543],
                                [-0.562977812819554, 44.8258767394756],
                                [-0.5625248198096813, 44.8256606526478],
                                [-0.5624339539551215, 44.825727942930854],
                                [-0.5628922920153343, 44.82595445471543],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"rnb_id": "SouthOne"},
                    "geometry": {
                        "coordinates": [
                            [
                                [-0.5625662439495045, 44.82549574373451],
                                [-0.5626891801060765, 44.825396229506396],
                                [-0.5624192550669704, 44.8253175657571],
                                [-0.5623524419395665, 44.82537348337317],
                                [-0.5624139100166587, 44.825409498080205],
                                [-0.5623885210289927, 44.82542845317994],
                                [-0.5624513253690111, 44.825468258869535],
                                [-0.5624820594081541, 44.825436982972775],
                                [-0.5625662439495045, 44.82549574373451],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"rnb_id": "BizarreShape"},
                    "geometry": {
                        "coordinates": [
                            [
                                [-0.5627678148564996, 44.82565292998436],
                                [-0.5628181401409904, 44.82561162752762],
                                [-0.5627836313742876, 44.825592760963474],
                                [-0.5628317998610441, 44.825551458463195],
                                [-0.562849054243145, 44.82556318633664],
                                [-0.5629166339110441, 44.82551321538125],
                                [-0.5628023236232309, 44.82544029850132],
                                [-0.5626477531075977, 44.825559107076515],
                                [-0.5626887322676168, 44.82558511235459],
                                [-0.5626757914797906, 44.825595820406534],
                                [-0.5627678148564996, 44.82565292998436],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 2,
                },
            ],
        }
        create_from_geojson(rnb_bdgs)

        # Add one address for testing address geocoding
        address_1 = Address.objects.create(
            id="BAN_ID_ONE",
            point=Point(-0.5628137581613334, 44.82584611733995, srid=4326),
        )

        # Add one address on two buildings to test ambiguous address
        address_2 = Address.objects.create(
            id="AMBIGUOUS_ADDRESS",
            point=Point(-0.562675427959789, 44.825661934374295, srid=4326),
        )

        bs = Building.objects.get(rnb_id="SouthOne")
        bs.addresses_id = [address_1.id, address_2.id]
        bs.save()

        bl = Building.objects.get(rnb_id="BigLong")
        bl.addresses_id = [address_2.id]
        bl.save()

    def _create_guess_work_file(self):
        # Let's be sure the file is not on disk
        if os.path.exists(self.WORK_FILE):
            os.remove(self.WORK_FILE)

        # Then create the Guesser work file
        inputs = [
            {
                "ext_id": "1",
                "lat": 44.82584611733995,
                "lng": -0.5628137581613334,
                "name": "Random urban place",
                "address": "75 Rue Malbec, 33800 Bordeaux",
            },
            {
                "ext_id": "2",
                "lat": 49.20900576719936,
                "lng": 3.4187047589154926,
                "name": "Random rural place",
                "address": "5 Rue des Deux Fermés, 02210 Beugneux",
            },
        ]

        guesser = Guesser()
        guesser.create_work_file(inputs, self.WORK_FILE)

    def test_work_file_creation(self):

        self.maxDiff = None

        # Verify the file has been created during the setup
        self.assertTrue(os.path.exists(self.WORK_FILE))

        # Finally, verify the content of the file
        with open(self.WORK_FILE, "r") as f:
            data = json.load(f)

            expected = {
                "1": {
                    "input": {
                        "ext_id": "1",
                        "lat": 44.82584611733995,
                        "lng": -0.5628137581613334,
                        "name": "Random urban place",
                        "address": "75 Rue Malbec, 33800 Bordeaux",
                    },
                    "matches": [],
                    "match_reason": None,
                    "finished_steps": [],
                },
                "2": {
                    "input": {
                        "ext_id": "2",
                        "lat": 49.20900576719936,
                        "lng": 3.4187047589154926,
                        "name": "Random rural place",
                        "address": "5 Rue des Deux Fermés, 02210 Beugneux",
                    },
                    "matches": [],
                    "match_reason": None,
                    "finished_steps": [],
                },
            }

            self.assertDictEqual(data, expected)

            # remove the work file
            os.remove(self.WORK_FILE)

    def test_ambiguous_point(self):
        # The point is almost equidistant from two buildings. It should not be matched.

        inputs = [
            {
                "ext_id": "AMBIGUOUS_POINT",
                "lat": 44.825661934374295,
                "lng": -0.562675427959789,
            }
        ]

        guesser = Guesser()
        guesser.load_inputs(inputs)
        guesser.guess_all()

        # We verify we found no building
        self.assertEqual(len(guesser.guesses.get("AMBIGUOUS_POINT")["matches"]), 0)
        self.assertEqual(
            guesser.guesses.get("AMBIGUOUS_POINT")["finished_steps"],
            ["closest_from_point", "geocode_address", "geocode_name"],
        )

    def test_point_on_building(self):
        guesser = Guesser()

        inputs = [
            {
                "ext_id": "UNIQUE_ROW",
                "lat": 44.8257,
                "lng": -0.5625,
                "name": "Not too far",
                "address": "1 rue nulle part, introuvable",
            }
        ]

        guesser.load_inputs(inputs)
        guesser.guess_all()

        # We verify we found the right building
        self.assertEqual(len(guesser.guesses.get("UNIQUE_ROW")["matches"]), 1)
        self.assertEqual(
            guesser.guesses.get("UNIQUE_ROW")["matches"][0].rnb_id, "BigLong"
        )

        # We check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "point_on_bdg")

    @patch("batid.services.geocoders.BanBatchGeocoder.geocode")
    def test_guess_from_address(self, geocode_mock):
        geocode_mock.return_value = _mock_guesser_batch_address_geocoding(
            [
                {
                    "ext_id": "UNIQUE_ROW",
                    "result_id": "BAN_ID_ONE",
                    "result_score": 0.9,
                },
                {
                    "ext_id": "UNIQUE_ROW",
                    "result_id": "BAN_ID_LESS_SCORE",
                    "result_score": 0.8,
                },
            ]
        )

        inputs = [
            {
                "ext_id": "UNIQUE_ROW",
                "lat": 44.8252,
                "lng": -0.5628,
                "name": "Very far",
                "address": "1 rue à géocoder, trouvable",
            }
        ]

        guesser = Guesser()
        guesser.load_inputs(inputs)
        guesser.guess_all()

        # We verify we found the right building
        self.assertEqual(
            guesser.guesses.get("UNIQUE_ROW")["matches"][0].rnb_id, "SouthOne"
        )
        self.assertEqual(len(guesser.guesses.get("UNIQUE_ROW")["matches"]), 1)

        # We check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "precise_address_match")

    @patch("batid.services.guess_bdg_new.GeocodeAddressHandler._geocode_batch")
    @patch("batid.services.guess_bdg_new.GeocodeNameHandler._geocode_name_and_point")
    def test_ambiguous_address(self, geocode_name_and_point_mock, geocode_batch_mock):
        geocode_name_and_point_mock.return_value = None

        inputs = [
            {
                "ext_id": "UNIQUE_ROW",
                "lat": 44.8252,
                "lng": -0.5628,
                "name": "Very far",
                "address": "1 rue à géocoder, trouvable mais ambigue",
            }
        ]

        guesser = Guesser()
        guesser.load_inputs(inputs)

        geocode_batch_mock.return_value = guesser.guesses
        guesser.guess_all()

        # We verify we found the right building
        self.assertEqual(len(guesser.guesses.get("UNIQUE_ROW")["matches"]), 0)
        self.assertEqual(
            guesser.guesses.get("UNIQUE_ROW")["finished_steps"],
            ["closest_from_point", "geocode_address", "geocode_name"],
        )

        # We check the match reason is empty
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertIsNone(reason)

    @patch("batid.services.guess_bdg_new.GeocodeNameHandler._geocode_name_and_point")
    def test_guess_from_name_on_building(self, geocode_name_and_point_mock):
        geocode_name_and_point_mock.return_value = Point(
            -0.5627717611330638, 44.825522167102605, srid=4326
        )

        inputs = [
            {
                "ext_id": "UNIQUE_ROW",
                "lat": 44.8254,
                "lng": -0.5630,
                "name": "On building",
            }
        ]

        guesser = Guesser()
        guesser.load_inputs(inputs)
        guesser.guess_all()

        # We verify we found the right building
        self.assertEqual(
            guesser.guesses.get("UNIQUE_ROW")["matches"][0].rnb_id, "BizarreShape"
        )
        self.assertEqual(len(guesser.guesses.get("UNIQUE_ROW")["matches"]), 1)

        # Check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "found_name_in_osm_point_on_bdg")

    @patch("batid.services.guess_bdg_new.GeocodeNameHandler._geocode_name_and_point")
    def test_guess_from_name_close_to_building(self, geocode_name_and_point_mock):
        geocode_name_and_point_mock.return_value = Point(
            -0.5623671471738305,
            44.82532433011028,
            srid=4326,
        )

        inputs = [
            {
                "ext_id": "UNIQUE_ROW",
                "lat": 44.8254,
                "lng": -0.5630,
                "name": "Not too far",
            }
        ]

        guesser = Guesser()
        guesser.load_inputs(inputs)
        guesser.guess_all()

        # We verify we found the right building
        self.assertEqual(
            guesser.guesses.get("UNIQUE_ROW")["matches"][0].rnb_id, "SouthOne"
        )
        self.assertEqual(len(guesser.guesses.get("UNIQUE_ROW")["matches"]), 1)

        # Check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "found_name_in_osm_isolated_closest_bdg")

    def test_lng_lat_bbox_around_point(self):
        lng, lat = 2.387349, 48.862927
        bbox = GeocodeNameHandler.lng_lat_bbox_around_point(lat, lng, 500)
        self.assertEqual(
            ["%.6f" % num for num in bbox],
            ["2.382857", "48.859972", "2.391841", "48.865882"],
        )

    def test_custom_handlers(self):
        # we define a custom list of handlers and check it is used
        inputs = [
            {
                "ext_id": "SOME_POINT",
                "lat": 44.82595445471543,
                "lng": -0.5628922920153343,
            }
        ]

        guesser = Guesser()
        # we only set only one handler
        guesser.handlers = [ClosestFromPointHandler()]
        guesser.load_inputs(inputs)
        guesser.guess_all()

        # We verify we found the right building
        self.assertEqual(len(guesser.guesses.get("SOME_POINT")["matches"]), 1)
        self.assertEqual(
            guesser.guesses.get("SOME_POINT")["matches"][0].rnb_id, "BigLong"
        )
        # only one handler has been called
        self.assertEqual(
            guesser.guesses.get("SOME_POINT")["finished_steps"], ["closest_from_point"]
        )


class PartialRoofTest(TransactionTestCase):
    input_poly_geojson = None

    def setUp(self):
        self._create_neighbourhood()

    def _trigger_guesser(self) -> Guesser:
        guesser = Guesser()
        guesser.handlers = [PartialRoofHandler()]

        inputs = [{"ext_id": "the_ext_id", "polygon": self.input_poly_geojson}]
        guesser.load_inputs(inputs)
        guesser.guess_all()

        return guesser

    def _create_neighbourhood(self):
        create_from_geojson(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "CORNERBDGBDG"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.728104105388297, 45.174788212790816],
                                    [5.7280665503610635, 45.174714899351756],
                                    [5.728307769189996, 45.17464973177127],
                                    [5.7283828792445775, 45.174788212790816],
                                    [5.728260103193975, 45.17481570530629],
                                    [5.728232659135443, 45.17476784795633],
                                    [5.728104105388297, 45.174788212790816],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 0,
                    },
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "LONGMIDDROOF"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.728254197073937, 45.17481850255783],
                                    [5.728384091173496, 45.174788108021346],
                                    [5.728469777617846, 45.174953931181165],
                                    [5.728333880009558, 45.17498394088963],
                                    [5.728254197073937, 45.17481850255783],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 1,
                    },
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "LONGTOPPROOF"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.728419334143354, 45.175141338271914],
                                    [5.728335115532474, 45.17498281606996],
                                    [5.728469691662923, 45.17495466150129],
                                    [5.7285495691088215, 45.175114407890504],
                                    [5.728482715159487, 45.175130321299264],
                                    [5.728419334143354, 45.175141338271914],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 2,
                    },
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "ALONESQUAREE"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.728031233946098, 45.17502321173117],
                                    [5.727996504621501, 45.174934463650175],
                                    [5.728138894850929, 45.174908757283674],
                                    [5.728171887708982, 45.17499872951552],
                                    [5.728105901992933, 45.17501280679065],
                                    [5.728031233946098, 45.17502321173117],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 3,
                    },
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "WWEIRDSHAPEE"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.7278219897474685, 45.17508013300099],
                                    [5.727776841625456, 45.174997505564676],
                                    [5.727834145010689, 45.17498159211877],
                                    [5.727845432040596, 45.174995669398186],
                                    [5.727911417756644, 45.174982816229885],
                                    [5.727932255351476, 45.175012194895686],
                                    [5.727939201216401, 45.17505136642592],
                                    [5.7278219897474685, 45.17508013300099],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 4,
                    },
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "TOMERGELEFTT"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.727848036740539, 45.1749112056701],
                                    [5.72777597339288, 45.17477900132201],
                                    [5.7278654014020844, 45.174755131059584],
                                    [5.7279357282839385, 45.1748946801433],
                                    [5.727848036740539, 45.1749112056701],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 5,
                    },
                    {
                        "type": "Feature",
                        "properties": {"rnb_id": "TOMERGERIGHT"},
                        "geometry": {
                            "coordinates": [
                                [
                                    [5.727936596517225, 45.17489406808653],
                                    [5.7278654014020844, 45.174755131059584],
                                    [5.727946147081298, 45.17472942461214],
                                    [5.728017342195642, 45.17487387021396],
                                    [5.727936596517225, 45.17489406808653],
                                ]
                            ],
                            "type": "Polygon",
                        },
                        "id": 6,
                    },
                ],
            }
        )


class TestContainedAlmostSimilar(PartialRoofTest):
    input_poly_geojson = {
        "coordinates": [
            [
                [5.7283368358221765, 45.17497972302533],
                [5.72826081259916, 45.174820222457896],
                [5.728382992779842, 45.174792150312015],
                [5.72846444623363, 45.17495101295626],
                [5.7283368358221765, 45.17497972302533],
            ]
        ],
        "type": "Polygon",
    }

    def setUp(self):
        self._create_neighbourhood()

    def test_result(self):
        guesser = self._trigger_guesser()

        matches = guesser.guesses["the_ext_id"]["matches"]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].rnb_id, "LONGMIDDROOF")
        self.assertEqual(matches[0].distance.m, 0)


class TestAlmostContainedAlmostSimilar(PartialRoofTest):
    input_poly_geojson = {
        "coordinates": [
            [
                [5.728410143118737, 45.17513858575376],
                [5.7283314047799365, 45.17498674164739],
                [5.728466255497636, 45.17496058358833],
                [5.728543183759285, 45.17511242776379],
                [5.728410143118737, 45.17513858575376],
            ]
        ],
        "type": "Polygon",
    }

    def setUp(self):
        self._create_neighbourhood()

    def test_result(self):
        guesser = self._trigger_guesser()

        matches = guesser.guesses["the_ext_id"]["matches"]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].rnb_id, "LONGTOPPROOF")
        self.assertEqual(matches[0].distance.m, 0)


class TestRoofCoveringManyBdgs(PartialRoofTest):
    input_poly_geojson = {
        "coordinates": [
            [
                [5.728418873838081, 45.1751438810538],
                [5.728236115185354, 45.17480653775482],
                [5.728376190073732, 45.17476585300025],
                [5.728557145188262, 45.175114215265694],
                [5.728418873838081, 45.1751438810538],
            ]
        ],
        "type": "Polygon",
    }

    def setUp(self):
        self._create_neighbourhood()

    def test_result(self):
        guesser = self._trigger_guesser()

        rnb_ids = [bdg.rnb_id for bdg in guesser.guesses["the_ext_id"]["matches"]]

        self.assertEqual(len(rnb_ids), 2)
        self.assertIn("LONGTOPPROOF", rnb_ids)
        self.assertIn("LONGMIDDROOF", rnb_ids)
        self.assertEqual(
            guesser.guesses["the_ext_id"]["match_reason"],
            "many_bdgs_covered_enough_by_roof",
        )


class TestAmbiguousRoofAttribution(PartialRoofTest):
    input_poly_geojson = {
        "coordinates": [
            [
                [5.727934924083456, 45.17488960238438],
                [5.728014279814005, 45.17486586964901],
                [5.728034118747701, 45.17492901565453],
                [5.727960173633761, 45.17493918681677],
                [5.727934924083456, 45.17488960238438],
            ]
        ],
        "type": "Polygon",
    }

    def setUp(self):
        self._create_neighbourhood()

    def test_result(self):
        guesser = self._trigger_guesser()

        matches = guesser.guesses["the_ext_id"]["matches"]

        self.assertEqual(len(matches), 0)
        self.assertIn(
            "partial_roof",
            guesser.guesses["the_ext_id"]["finished_steps"],
        )


class TestIsolatedMatching(PartialRoofTest):
    input_poly_geojson = {
        "coordinates": [
            [
                [5.727809551942045, 45.175076186174834],
                [5.727825225381423, 45.17507291243297],
                [5.727836545086944, 45.175096442448336],
                [5.727800263977912, 45.175102376102956],
                [5.727791556511136, 45.175079050699054],
                [5.727809551942045, 45.175076186174834],
            ]
        ],
        "type": "Polygon",
    }

    def setUp(self):
        self._create_neighbourhood()

    def test_result(self):
        guesser = self._trigger_guesser()

        matches = guesser.guesses["the_ext_id"]["matches"]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].rnb_id, "WWEIRDSHAPEE")
        self.assertEqual(matches[0].distance.m, 0)


class TestAddressGeocoding(TransactionTestCase):
    def setUp(self):

        Address.objects.create(id="BAN_ID_ONE")
        Address.objects.create(id="BAN_ID_TWO")
        Address.objects.create(id="BAN_ID_THREE")

        b = create_default_bdg(rnb_id="BDG_ONE")
        b.addresses_id = ["BAN_ID_ONE"]
        b.save()

        b = create_default_bdg(rnb_id="BDG_TWO")
        b.addresses_id = ["BAN_ID_ONE", "BAN_ID_TWO"]
        b.save()

        b = create_default_bdg(rnb_id="BDG_THREE")

    @patch("batid.services.geocoders.BanBatchGeocoder.geocode")
    def test_find_bdgs(self, geocode_mock):

        geocode_mock.return_value = _mock_guesser_batch_address_geocoding(
            [{"ext_id": "line_1", "result_id": "BAN_ID_ONE"}]
        )

        guesser = Guesser()
        guesser.handlers = [GeocodeAddressHandler()]

        guesser.load_inputs(
            [{"ext_id": "line_1", "address": "1 rue de la paix, 75001 Paris"}]
        )

        guesser.guess_all()

        self.assertEqual(guesser.guesses["line_1"]["matches"][0].rnb_id, "BDG_ONE")
        self.assertEqual(guesser.guesses["line_1"]["matches"][1].rnb_id, "BDG_TWO")

    @patch("batid.services.geocoders.BanBatchGeocoder.geocode")
    def test_low_score(self, geocode_mock):
        geocode_mock.return_value = _mock_guesser_batch_address_geocoding(
            [{"ext_id": "line_1", "result_id": "BAN_ID_ONE", "result_score": 0.1}]
        )

        guesser = Guesser()
        guesser.handlers = [GeocodeAddressHandler()]

        guesser.load_inputs(
            [{"ext_id": "line_1", "address": "1 rue de la paix, 75001 Paris"}]
        )

        guesser.guess_all()

        self.assertEqual(len(guesser.guesses["line_1"]["matches"]), 0)

    @patch("batid.services.geocoders.BanBatchGeocoder.geocode")
    def test_street_type(self, geocode_mock):
        geocode_mock.return_value = _mock_guesser_batch_address_geocoding(
            [
                {
                    "ext_id": "line_1",
                    "result_id": "BAN_ID_ONE",
                    "result_type": "street",
                }
            ]
        )

        guesser = Guesser()
        guesser.handlers = [GeocodeAddressHandler()]

        guesser.load_inputs(
            [{"ext_id": "line_1", "address": "Rue de la paix, 75001 Paris"}]
        )

        guesser.guess_all()

        self.assertEqual(len(guesser.guesses["line_1"]["matches"]), 0)

    @patch("batid.services.geocoders.BanBatchGeocoder.geocode")
    def test_no_bdg_w_ban_id(self, geocode_mock):
        geocode_mock.return_value = _mock_guesser_batch_address_geocoding(
            [{"ext_id": "line_1", "result_id": "BAN_ID_XXX", "result_score": 0.9}]
        )

        guesser = Guesser()
        guesser.handlers = [GeocodeAddressHandler()]

        guesser.load_inputs(
            [{"ext_id": "line_1", "address": "42 rue de la réponse, 75001 Paris"}]
        )

        guesser.guess_all()

        self.assertEqual(len(guesser.guesses["line_1"]["matches"]), 0)


def _mock_guesser_batch_address_geocoding(data):

    for d in data:

        if "result_type" not in d:
            d["result_type"] = "housenumber"

        if "result_id" not in d:
            d["result_id"] = "dummy_ban_id"

        if "result_score" not in d:
            d["result_score"] = 0.9

    r = Response()
    r.status_code = 200

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

    r._content = buffer.getvalue().encode()

    return r
