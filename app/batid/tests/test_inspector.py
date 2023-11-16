import json
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from batid.models import BuildingStatus, Candidate, Address, Building
from batid.services.candidate import Inspector
from batid.services.rnb_id import generate_rnb_id
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


class InspectTest(TestCase):
    bdgs_data = None
    candidates_data = None

    def setUp(self):
        # Install buildings
        data_to_bdg(self.bdgs_data)

        # Install candidates
        data_to_candidate(self.candidates_data)


class OneSmallOneBig:

    """
    It should be the same building
    """

    small = {
        "id": "SMALL",
        "source": "bdtopo",
        "geometry": {
            "coordinates": [
                [
                    [
                        [5.721177215887707, 45.184501849070074],
                        [5.721149366402955, 45.184478272952845],
                        [5.7211919623955225, 45.184446041948206],
                        [5.721215837288156, 45.18447566001382],
                        [5.721177215887707, 45.184501849070074],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        },
    }
    big = {
        "id": "BIG",
        "source": "bdnb_7",
        "geometry": {
            "coordinates": [
                [
                    [
                        [5.721148095508113, 45.18447830212273],
                        [5.721199626357475, 45.18443878926573],
                        [5.721232796912972, 45.18446583051127],
                        [5.72117683962378, 45.18450291605984],
                        [5.721148095508113, 45.18447830212273],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        },
    }


class TestOneSmallBdgThenOneBigCand(InspectTest):
    bdgs_data = [OneSmallOneBig.small]
    candidates_data = [OneSmallOneBig.big]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)


class TestOneBigBdgThenOneSmallCand(InspectTest):
    bdgs_data = [OneSmallOneBig.big]
    candidates_data = [OneSmallOneBig.small]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)


class TestOneVeryBigBdgThenTwoSmallCandIn(InspectTest):

    """
    We build one large building, then two small candidates (half of the big building) in it.
    """

    bdgs_data = [
        {
            "id": "ONE_BIG",
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
        }
    ]

    candidates_data = [
        {
            "id": "SMALL_FIRST",
            "source": "bdnb_7",
            "geometry": {
                "coordinates": [
                    [
                        [
                            [5.721127230863317, 45.18446238615837],
                            [5.721074752083183, 45.18442146200806],
                            [5.721125267131185, 45.184388100687755],
                            [5.721176047710884, 45.18442771791334],
                            [5.721127230863317, 45.18446238615837],
                        ]
                    ]
                ],
                "type": "MultiPolygon",
            },
        },
        {
            "id": "SMALL_SECOND",
            "source": "bdnb_7",
            "geometry": {
                "coordinates": [
                    [
                        [
                            [5.721074037499392, 45.1844203689505],
                            [5.72102999800714, 45.18438590314449],
                            [5.721059494893126, 45.18434024050961],
                            [5.7211238095471515, 45.184388041217744],
                            [5.721074037499392, 45.1844203689505],
                        ]
                    ]
                ],
                "type": "MultiPolygon",
            },
        },
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)


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


def data_to_bdg(data):
    for d in data:
        shape = GEOSGeometry(json.dumps(d["geometry"]))
        shape.srid = 4326

        shape = shape.transform(2154, clone=True)

        Building.objects.create(
            rnb_id=generate_rnb_id(),
            shape=shape,
            source=d["source"],
            point=shape.point_on_surface,
        )


class TestInspectorFictiveBdgCreate(TestCase):
    def setUp(self) -> None:
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
            address_keys=["add_1"],
            is_light=False,
            # this building shape is tagged as fictive
            is_shape_fictive=True,
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

    def test_creation(self):
        i = Inspector()
        i.inspect()

        # Check all candidates have been inspected
        c_count = Candidate.objects.filter(inspected_at__isnull=True).count()
        self.assertEqual(c_count, 0)

        # Check we have only one building
        b_count = Building.objects.all().count()
        self.assertEqual(b_count, 1)

        b = Building.objects.all().first()

        # we expect the saved shape to be a point, because the shape has been discarded
        self.assertEqual(b.shape.geom_type, "Point")
        self.assertEqual(b.shape, b.point)
