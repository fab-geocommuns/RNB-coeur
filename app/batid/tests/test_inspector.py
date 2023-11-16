import json
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from batid.models import BuildingStatus, Candidate, Address, Building
from batid.services.candidate import Inspector
from batid.tests.helpers import (
    create_paris,
    create_constructed_bdg,
    coords_to_mp_geom,
    coords_to_point_geom,
)


class InspectTest(TestCase):
    bdgs_data = None
    candidates_data = None

    def setUp(self):
        i = Inspector()

        # Install buildings
        data_to_candidate(self.bdgs_data)
        i.inspect()

        # Install candidates
        data_to_candidate(self.candidates_data)
        i.inspect()


class TestInspectorBdgCreate(TestCase):
    def setUp(self) -> None:
        # The city
        create_paris()

        # The candidate
        coords = [
            [2.349804906833981, 48.85789205519228],
            [2.349701279442314, 48.85786369735885],
            [2.3496535925009994, 48.85777922711969],
            [2.349861764341199, 48.85773095834841],
            [2.3499452164882086, 48.857847406681174],
            [2.349804906833981, 48.85789205519228],
        ]
        Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdnb",
            source_id="bdnb_1",
            address_keys=["add_1", "add_2"],
            is_light=False,
        )

        # Create the addresses
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_2",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_rep="bis",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

    def test_creation(self):
        i = Inspector()
        i.inspect()

        # Check we have zero not inspected candidates
        c_count = Candidate.objects.filter(inspected_at__isnull=True).count()
        self.assertEqual(c_count, 0)

        # Check we have only one building
        b_count = Building.objects.all().count()
        self.assertEqual(b_count, 1)

        # Check the building has two adresses
        b = Building.objects.all().first()
        self.assertEqual(b.addresses.count(), 2)
        addresses_ids = [a.id for a in b.addresses.all()]
        self.assertIn("add_1", addresses_ids)
        self.assertIn("add_2", addresses_ids)

        # Check the ext_ids are correct
        self.assertEqual(b.ext_bdnb_id, "bdnb_1")
        self.assertEqual(b.ext_bdtopo_id, "")


class TestInspectorSimilarBdgUpdate(TestCase):
    def setUp(self):
        # Create the city
        create_paris()

        # Create an existing building
        coords = [
            [2.349804906833981, 48.85789205519228],
            [2.349701279442314, 48.85786369735885],
            [2.3496535925009994, 48.85777922711969],
            [2.349861764341199, 48.85773095834841],
            [2.3499452164882086, 48.857847406681174],
            [2.349804906833981, 48.85789205519228],
        ]
        create_constructed_bdg("EXISTING", coords)

        # Create a candidate for the merge
        Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdnb",
            source_id="bdnb_1",
            address_keys=["add_1", "add_2"],
            is_light=False,
        )
        Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdtopo",
            source_id="bdtopo_1",
            address_keys=["add_1", "add_3"],
            is_light=False,
        )

        # Create the addresses
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_2",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_rep="bis",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_3",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

    def test_merge(self):
        i = Inspector()
        i.inspect()

        # Check we have zero not inspected candidates
        c_count = Candidate.objects.filter(inspected_at__isnull=True).count()
        self.assertEqual(c_count, 0)

        # Check we have only one building
        b_count = Building.objects.all().count()
        self.assertEqual(b_count, 1)

        # Check the building has three adresses
        b = Building.objects.get(rnb_id="EXISTING")
        self.assertEqual(b.addresses.count(), 3)

        addresses_ids = [a.id for a in b.addresses.all()]
        self.assertIn("add_1", addresses_ids)
        self.assertIn("add_2", addresses_ids)
        self.assertIn("add_3", addresses_ids)

        # Check the ext_ids are correct
        self.assertEqual(b.ext_bdnb_id, "bdnb_1")
        self.assertEqual(b.ext_bdtopo_id, "bdtopo_1")


class TestDifferentBdgUpdateBDNBFirst(TestCase):
    def setUp(self):
        # BDNB first
        data = get_bdnb_data()
        data_to_candidate(data, "bdnb")
        i = Inspector()
        i.inspect()

    def test_bdg_count(self):
        data = get_bdtopo_data()
        data_to_candidate(data, "bdtopo")
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 5)


class TestDifferentBdgUpdateBDTOPOFirst(TestCase):
    def setUp(self):
        # BDTOPO first
        data = get_bdtopo_data()
        data_to_candidate(data, "bdtopo")
        i = Inspector()
        i.inspect()

    def test_bdg_count(self):
        data = get_bdnb_data()
        data_to_candidate(data, "bdnb")
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 5)


def get_bdtopo_data():
    return [
        {
            "id": "BIGWITHTWOSMALLBDNB",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [
                            [5.721127187330495, 45.18446405767136],
                            [5.721027107406655, 45.18438595665771],
                            [5.7210547676878605, 45.18433278646597],
                            [5.721178484578388, 45.184427074905244],
                            [5.721127187330495, 45.18446405767136],
                        ]
                    ]
                ],
                "type": "MultiPolygon",
            },
        },
        {
            "id": "BATIMENT0000000302575039",
            "source": "bdtopo",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446567095530989, 45.563882051003191],
                            [5.446566272053017, 45.563834320894699],
                            [5.446479062088596, 45.563834417687929],
                            [5.446489410789785, 45.563894553118274],
                            [5.446567095530989, 45.563882051003191],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575040",
            "source": "bdtopo",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446565642538875, 45.564023524933795],
                            [5.446567095530989, 45.563882051003191],
                            [5.446489410789785, 45.563894553118274],
                            [5.446494525580388, 45.563923270770559],
                            [5.446501925057774, 45.563945632340257],
                            [5.446514817823322, 45.563947153472974],
                            [5.446509104911867, 45.564021152164926],
                            [5.446565642538875, 45.564023524933795],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575042",
            "source": "bdtopo",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446679127470079, 45.563892224601396],
                            [5.446737671611675, 45.563881940905674],
                            [5.446684273685366, 45.563834454549664],
                            [5.446636059666131, 45.563846315129126],
                            [5.446679127470079, 45.563892224601396],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575043",
            "source": "bdtopo",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446659418339343, 45.56402688875653],
                            [5.446713353591003, 45.564028417202969],
                            [5.446847070125796, 45.563977757786169],
                            [5.446737671611675, 45.563881940905674],
                            [5.446679127470079, 45.563892224601396],
                            [5.446659418339343, 45.56402688875653],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302576336",
            "source": "bdtopo",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446399913390336, 45.564017222902208],
                            [5.446457732344438, 45.564019567831508],
                            [5.446470516543454, 45.563989559611706],
                            [5.446468660638516, 45.563918428415406],
                            [5.446454446835896, 45.56391603513007],
                            [5.446452728675052, 45.563906162564791],
                            [5.446437233543159, 45.563903797171726],
                            [5.44643250532324, 45.563912909166717],
                            [5.446399913390336, 45.564017222902208],
                        ]
                    ]
                ],
            },
        },
    ]


def get_bdnb_data():
    return [
        {
            "id": "BATIMENT0000000302575039-1",
            "source": "bdnb",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446489410789785, 45.563894553118274],
                            [5.446567095530989, 45.563882051003191],
                            [5.446566576972527, 45.563851994529756],
                            [5.44648200906015, 45.563851542304569],
                            [5.446489410789785, 45.563894553118274],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575040-2",
            "source": "bdnb",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.446494525580388, 45.563923270770559],
                            [5.446501925057774, 45.563945632340257],
                            [5.446514817823322, 45.563947153472974],
                            [5.446513473983935, 45.563964560089353],
                            [5.4465158, 45.563964699999978],
                            [5.446511543211344, 45.564021254495962],
                            [5.446565642538875, 45.564023524933795],
                            [5.446566913778149, 45.563899747827314],
                            [5.446492549183112, 45.563912174036382],
                            [5.446494525580388, 45.563923270770559],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575043-1",
            "source": "bdnb",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.44666325246629, 45.564026997410949],
                            [5.446713353591003, 45.564028417202969],
                            [5.446833329075726, 45.563982963687835],
                            [5.446739, 45.563900099999984],
                            [5.4466803, 45.5639101],
                            [5.44666325246629, 45.564026997410949],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302576336-1",
            "source": "bdnb",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [5.4464554, 45.5639344],
                            [5.4464531, 45.563924],
                            [5.446438, 45.563922099999978],
                            [5.4464336, 45.563930899999974],
                            [5.44640656059137, 45.564017492490358],
                            [5.446457732344438, 45.564019567831508],
                            [5.446470516543454, 45.563989559611706],
                            [5.446469133807057, 45.563936563544985],
                            [5.4464554, 45.5639344],
                        ]
                    ]
                ],
            },
        },
        # This is an hexagon (vitual shape) that we don't handle in this branch
        # {
        #     "id": "u05g5ywhugr2uupdqg4p38509000AI0471",
        #     "geometry": {
        #         "type": "MultiPolygon",
        #         "coordinates": [
        #             [
        #                 [
        #                     [890823.250357993296348, 6498999.213679479435086],
        #                     [890824.808165574562736, 6498996.515477600507438],
        #                     [890827.923780737095512, 6498996.515477600507438],
        #                     [890829.481588318361901, 6498999.213679479435086],
        #                     [890827.923780737095512, 6499001.911881358362734],
        #                     [890824.808165574562736, 6499001.911881358362734],
        #                     [890823.250357993296348, 6498999.213679479435086],
        #                 ]
        #             ]
        #         ],
        #     },
        # },
    ]


def data_to_candidate(data):
    for d in data:
        shape = GEOSGeometry(json.dumps(d["geometry"]))
        shape.srid = 4326

        shape = shape.transform(2154, clone=True)

        Candidate.objects.create(
            shape=shape,
            source=d["source"],
            source_id=d["id"],
            is_light=False,
        )
