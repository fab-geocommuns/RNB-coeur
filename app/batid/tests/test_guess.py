import json
import os
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TransactionTestCase

from batid.models import Address
from batid.models import Building
from batid.services.guess_bdg_new import ClosestFromPointHandler
from batid.services.guess_bdg_new import Guesser
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
                    "match": None,
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
                    "match": None,
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

        # We verify we found the right building
        matching_bdg = guesser.guesses.get("AMBIGUOUS_POINT")["match"]
        self.assertIsNone(matching_bdg)
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
        matching_bdg = guesser.guesses.get("UNIQUE_ROW")["match"]
        self.assertEqual(matching_bdg.rnb_id, "BigLong")

        # We check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "point_on_bdg")

    @patch("batid.services.guess_bdg_new.GeocodeAddressHandler._address_to_ban_id")
    @patch("batid.services.guess_bdg_new.GeocodeNameHandler._geocode_name_and_point")
    def test_guess_from_address(
        self, geocode_name_and_point_mock, address_to_ban_id_mock
    ):
        geocode_name_and_point_mock.return_value = None
        address_to_ban_id_mock.return_value = "BAN_ID_ONE"

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
        matching_bdg = guesser.guesses.get("UNIQUE_ROW")["match"]
        self.assertEqual(matching_bdg.rnb_id, "SouthOne")

        # We check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "precise_address_match")

    @patch("batid.services.guess_bdg_new.GeocodeAddressHandler._address_to_ban_id")
    @patch("batid.services.guess_bdg_new.GeocodeNameHandler._geocode_name_and_point")
    def test_ambiguous_address(
        self, geocode_name_and_point_mock, address_to_ban_id_mock
    ):
        geocode_name_and_point_mock.return_value = None
        address_to_ban_id_mock.return_value = "AMBIGUOUS_ADDRESS"

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
        guesser.guess_all()

        # We verify we found the right building
        matching_bdg = guesser.guesses.get("UNIQUE_ROW")["match"]
        self.assertIsNone(matching_bdg)
        self.assertEqual(
            guesser.guesses.get("UNIQUE_ROW")["finished_steps"],
            ["closest_from_point", "geocode_address", "geocode_name"],
        )

        # We check the match reason is empty
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertIsNone(reason)

    @patch("batid.services.guess_bdg_new.GeocodeNameHandler._geocode_name_and_point")
    def test_guess_from_name(self, geocode_name_and_point_mock):
        geocode_name_and_point_mock.return_value = Point(
            -0.5627717611330638, 44.825522167102605, srid=4326
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
        matching_bdg = guesser.guesses.get("UNIQUE_ROW")["match"]
        self.assertEqual(matching_bdg.rnb_id, "BizarreShape")

        # Check the reason
        reason = guesser.guesses.get("UNIQUE_ROW")["match_reason"]
        self.assertEqual(reason, "found_name_in_osm")

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
        matching_bdg = guesser.guesses.get("SOME_POINT")["match"]
        self.assertEqual(matching_bdg.rnb_id, "BigLong")
        # only one handler has been called
        self.assertEqual(
            guesser.guesses.get("SOME_POINT")["finished_steps"], ["closest_from_point"]
        )
