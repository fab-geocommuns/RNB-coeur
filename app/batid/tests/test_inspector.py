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
            "id": "BATIMENT0000000302575039",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890817.099999999976717, 6498998.900000000372529],
                            [890817.199999999953434, 6498993.599999999627471],
                            [890810.400000000023283, 6498993.400000000372529],
                            [890811.0, 6499000.099999999627471],
                            [890817.099999999976717, 6498998.900000000372529],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575040",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890816.5, 6499014.599999999627471],
                            [890817.099999999976717, 6498998.900000000372529],
                            [890811.0, 6499000.099999999627471],
                            [890811.300000000046566, 6499003.299999999813735],
                            [890811.800000000046566, 6499005.799999999813735],
                            [890812.800000000046566, 6499006.0],
                            [890812.099999999976717, 6499014.200000000186265],
                            [890816.5, 6499014.599999999627471],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575042",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890825.800000000046566, 6499000.299999999813735],
                            [890830.400000000023283, 6498999.299999999813735],
                            [890826.400000000023283, 6498993.900000000372529],
                            [890822.599999999976717, 6498995.099999999627471],
                            [890825.800000000046566, 6499000.299999999813735],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575043",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890823.800000000046566, 6499015.200000000186265],
                            [890828.0, 6499015.5],
                            [890838.599999999976717, 6499010.200000000186265],
                            [890830.400000000023283, 6498999.299999999813735],
                            [890825.800000000046566, 6499000.299999999813735],
                            [890823.800000000046566, 6499015.200000000186265],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302576336",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890803.599999999976717, 6499013.5],
                            [890808.099999999976717, 6499013.900000000372529],
                            [890809.199999999953434, 6499010.599999999627471],
                            [890809.300000000046566, 6499002.700000000186265],
                            [890808.199999999953434, 6499002.400000000372529],
                            [890808.099999999976717, 6499001.299999999813735],
                            [890806.900000000023283, 6499001.0],
                            [890806.5, 6499002.0],
                            [890803.599999999976717, 6499013.5],
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
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890811.0, 6499000.099999999627471],
                            [890817.099999999976717, 6498998.900000000372529],
                            [890817.162971726502292, 6498995.562498493120074],
                            [890810.570860504289158, 6498995.307942297309637],
                            [890811.0, 6499000.099999999627471],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575040-2",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890811.300000000046566, 6499003.299999999813735],
                            [890811.800000000046566, 6499005.799999999813735],
                            [890812.800000000046566, 6499006.0],
                            [890812.635339907137677, 6499007.928875373676419],
                            [890812.816215125727467, 6499007.950026175007224],
                            [890812.289758904022165, 6499014.217250810004771],
                            [890816.5, 6499014.599999999627471],
                            [890817.024946635006927, 6499000.863896384835243],
                            [890811.184077562415041, 6499002.063493998721242],
                            [890811.300000000046566, 6499003.299999999813735],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302575043-1",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890824.098567877197638, 6499015.221326276659966],
                            [890828.0, 6499015.5],
                            [890837.510716237593442, 6499010.74464188143611],
                            [890830.441095866495743, 6499001.318857489153743],
                            [890825.829921292024665, 6499002.286990765482187],
                            [890824.098567877197638, 6499015.221326276659966],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "BATIMENT0000000302576336-1",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890808.211139371152967, 6499004.440791579894722],
                            [890808.067588575766422, 6499003.280840700492263],
                            [890806.89679592102766, 6499003.033453833311796],
                            [890806.523460239404812, 6499003.999615712091327],
                            [890804.117346019716933, 6499013.54598631337285],
                            [890808.099999999976717, 6499013.900000000372529],
                            [890809.199999999953434, 6499010.599999999627471],
                            [890809.274504675064236, 6499004.71413066983223],
                            [890808.211139371152967, 6499004.440791579894722],
                        ]
                    ]
                ],
            },
        },
        {
            "id": "u05g5ywhugr2uupdqg4p38509000AI0471",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [890823.250357993296348, 6498999.213679479435086],
                            [890824.808165574562736, 6498996.515477600507438],
                            [890827.923780737095512, 6498996.515477600507438],
                            [890829.481588318361901, 6498999.213679479435086],
                            [890827.923780737095512, 6499001.911881358362734],
                            [890824.808165574562736, 6499001.911881358362734],
                            [890823.250357993296348, 6498999.213679479435086],
                        ]
                    ]
                ],
            },
        },
    ]


def data_to_candidate(data, source):
    for d in data:
        shape = GEOSGeometry(json.dumps(d["geometry"]))
        shape.srid = 2154

        Candidate.objects.create(
            shape=shape,
            source=source,
            source_id=d["id"],
            is_light=False,
        )
