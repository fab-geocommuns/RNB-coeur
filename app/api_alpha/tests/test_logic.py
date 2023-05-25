from rest_framework.test import APITestCase
from api_alpha.logic import calc_ads_cities
from api_alpha.tests.helpers import create_bdg, create_paris, create_grenoble


class LogicTest(APITestCase):
    def test_calc_cities_point_grenoble(self):
        data = {
            "buildings_operations": [
                {
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "coordinates": [5.724331358994107, 45.18157371019683],
                            "type": "Point",
                        },
                    }
                }
            ]
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "38185")

    def test_calc_existing_and_new(self):
        data = {
            "buildings_operations": [
                {"building": {"rnb_id": "ONE1ONE1ONE1"}},
                {
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "coordinates": [2.36107202146934, 48.84551122951689],
                            "type": "Point",
                        },
                    }
                },
            ],
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 2)
        self.assertEqual(cities[0].code_insee, "38185")
        self.assertEqual(cities[1].code_insee, "75056")

    def test_calc_one_new_bdg_multipolygon_paris(self):
        data = {
            "buildings_operations": [
                {
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "coordinates": [
                                [
                                    [
                                        [2.342150687705498, 48.827855733036756],
                                        [2.342094227074142, 48.827759092595244],
                                        [2.342231144105199, 48.8277293570373],
                                        [2.342335596272477, 48.82792821324557],
                                        [2.342221263494281, 48.82794865636265],
                                        [2.342150687705498, 48.827855733036756],
                                    ]
                                ]
                            ],
                            "type": "MultiPolygon",
                        },
                    }
                }
            ]
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "75056")

    def test_calc_one_new_bdg_multipolygon_grenoble(self):
        data = {
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "coordinates": [
                                [
                                    [
                                        [5.736498177543439, 45.18740370893255],
                                        [5.736455101954846, 45.18732521910442],
                                        [5.736581176848205, 45.187335585691784],
                                        [5.736620049940626, 45.187404449402266],
                                        [5.736498177543439, 45.18740370893255],
                                    ]
                                ]
                            ],
                            "type": "MultiPolygon",
                        },
                    },
                }
            ]
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "38185")

    def test_calc_one_new_bdg_point_paris(self):
        data = {
            "file_number": "ADS-TEST-NEW-BDG",
            "decision_date": "2019-03-18",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [2.3552747458487002, 48.86958288638419],
                        },
                    },
                }
            ],
        }
        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "75056")

    def test_calc_one_new_bdg_point(self):
        data = {
            "buildings_operations": [
                {
                    "building": {
                        "rnb_id": "new",
                        "geometry": {
                            "coordinates": [2.36107202146934, 48.84551122951689],
                            "type": "Point",
                        },
                    }
                }
            ]
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "75056")

    def test_calc_two_bdg_two_city(self):
        data = {
            "buildings_operations": [
                {"building": {"rnb_id": "ONE1ONE1ONE1"}},
                {"building": {"rnb_id": "PARIPARIPARI"}},
            ]
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 2)
        self.assertEqual(cities[0].code_insee, "38185")
        self.assertEqual(cities[1].code_insee, "75056")

    def test_calc_two_bdg_one_city(self):
        data = {
            "buildings_operations": [
                {"building": {"rnb_id": "ONE1ONE1ONE1"}},
                {"building": {"rnb_id": "TWO2TWO2TWO2"}},
            ]
        }

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "38185")

    def test_calc_one_bdg_one_city(self):
        data = {"buildings_operations": [{"building": {"rnb_id": "ONE1ONE1ONE1"}}]}

        cities = calc_ads_cities(data)

        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0].code_insee, "38185")

    def setUp(self) -> None:
        # ########
        # ONE - Grenoble
        coords = [
            [5.717918517856731, 45.178820091145724],
            [5.718008279271032, 45.17865980057857],
            [5.7184092135875915, 45.17866401875747],
            [5.7184451181529425, 45.17884961830637],
            [5.717924501950705, 45.17893819969589],
            [5.717918517856731, 45.178820091145724],
        ]
        create_bdg("ONE1ONE1ONE1", coords)

        # ########
        # TWO - Grenoble
        coords = [
            [5.742707274322839, 45.16421731700598],
            [5.74266854803281, 45.164130851028034],
            [5.742765363759105, 45.16408079171745],
            [5.742903057235566, 45.16416422387715],
            [5.7428385134176665, 45.16425372369457],
            [5.742707274322839, 45.16421731700598],
        ]
        create_bdg("TWO2TWO2TWO2", coords)

        # ########
        # Paris
        coords = [
            [2.361039252873155, 48.845725881287876],
            [2.360949242086434, 48.84565761029228],
            [2.3610636625784878, 48.845598375087775],
            [2.3611719806437748, 48.84565761029228],
            [2.3611719806437748, 48.84574395300689],
            [2.361039252873155, 48.845725881287876],
        ]
        create_bdg("PARIPARIPARI", coords)

        create_grenoble()
        create_paris()
