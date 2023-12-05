import json
from datetime import datetime
from django.contrib.gis.geos import GEOSGeometry, Point, Polygon
from django.test import TestCase
from batid.models import BuildingStatus, Candidate, Address, Building, BuildingImport
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
            source_version="7.2",
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

        self.assertEqual(len(b.ext_ids), 1)
        self.assertEqual(b.ext_ids[0]["source"], "bdnb")
        self.assertEqual(b.ext_ids[0]["source_version"], "7.2")
        self.assertEqual(b.ext_ids[0]["id"], "bdnb_1")

        # check the candidate inspection_details is set
        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "creation")
        self.assertEqual(candidate.inspection_details["rnb_id"], b.rnb_id)


class TestInspectorBdgUpdate(TestCase):
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
        b = create_constructed_bdg("EXISTING", coords)
        b.add_ext_id("bdnb", "7.2", "bdnb_previous", datetime.now().isoformat())
        b.save()

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
        self.assertEqual(len(b.ext_ids), 3)

        self.assertEqual(b.ext_ids[0]["source"], "bdnb")
        self.assertEqual(b.ext_ids[0]["source_version"], "7.2")
        self.assertEqual(b.ext_ids[0]["id"], "bdnb_previous")

        self.assertEqual(b.ext_ids[1]["source"], "bdnb")
        self.assertEqual(b.ext_ids[1]["source_version"], None)
        self.assertEqual(b.ext_ids[1]["id"], "bdnb_1")

        self.assertEqual(b.ext_ids[2]["source"], "bdtopo")
        self.assertEqual(b.ext_ids[2]["source_version"], None)
        self.assertEqual(b.ext_ids[2]["id"], "bdtopo_1")

        # Check the candidate inspection_details is set
        first_candidate = Candidate.objects.all().order_by("inspected_at").first()
        second_candidate = Candidate.objects.all().order_by("inspected_at").last()

        self.assertEqual(first_candidate.inspection_details["decision"], "update")
        self.assertEqual(first_candidate.inspection_details["rnb_id"], b.rnb_id)

        self.assertEqual(second_candidate.inspection_details["decision"], "update")
        self.assertEqual(second_candidate.inspection_details["rnb_id"], b.rnb_id)


class InspectTest(TestCase):
    bdgs_data = None
    candidates_data = None

    def setUp(self):
        # Install buildings
        data_to_bdg(self.bdgs_data)

        # Install candidates
        data_to_candidate(self.candidates_data)


class TestHalvishCover(InspectTest):

    """
    We the the case where the candidate partially cover an existing building. Not enough to consider it as the same building but enought to be ambiguous.
    It should result with the rejection of the candidate.
    """

    bdgs_data = [
        {
            "id": "BX_SQUARE",
            "source": "dummy",
            "geometry": {
                "coordinates": [
                    [
                        [
                            [-0.5676725429616454, 44.838295594794175],
                            [-0.5678845217807691, 44.838295594794175],
                            [-0.5678845217807691, 44.838147629163586],
                            [-0.5676725429616454, 44.838147629163586],
                            [-0.5676725429616454, 44.838295594794175],
                        ]
                    ]
                ],
                "type": "MultiPolygon",
            },
        }
    ]

    candidates_data = [
        {
            "id": "SECOND_SQUARE",
            "source": "dummy",
            "geometry": {
                "coordinates": [
                    [
                        [
                            [-0.5675952590175939, 44.83808812964935],
                            [-0.5675952590175939, 44.83824470718619],
                            [-0.5678083418932829, 44.83824470718619],
                            [-0.5678083418932829, 44.83808812964935],
                            [-0.5675952590175939, 44.83808812964935],
                        ]
                    ]
                ],
                "type": "MultiPolygon",
            },
        }
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")
        self.assertEqual(candidate.inspection_details["reason"], "ambiguous_overlap")


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

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)


class TestOneSmallBdgThenOneBigCand(InspectTest):
    bdgs_data = [OneSmallOneBig.small]
    candidates_data = [OneSmallOneBig.big]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")
        self.assertEqual(candidate.inspection_details["reason"], "ambiguous_overlap")


class TestOneBigBdgThenOneSmallCand(InspectTest):
    bdgs_data = [OneSmallOneBig.big]
    candidates_data = [OneSmallOneBig.small]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")


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

        candidate = Candidate.objects.all().order_by("inspected_at").first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")
        self.assertEqual(candidate.inspection_details["reason"], "ambiguous_overlap")

        candidate_2 = Candidate.objects.all().order_by("inspected_at").last()
        self.assertEqual(candidate_2.inspection_details["decision"], "refusal")
        self.assertEqual(candidate_2.inspection_details["reason"], "ambiguous_overlap")


class TestPointCandidateInsidePolyBdg(InspectTest):
    bdgs_data = [
        {
            "id": "POLY_BDG",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [-0.567884072259659, 44.83820534369249],
                        [-0.567884072259659, 44.838091952624836],
                        [-0.5676364726049883, 44.838091952624836],
                        [-0.5676364726049883, 44.83820534369249],
                        [-0.567884072259659, 44.83820534369249],
                    ]
                ],
                "type": "Polygon",
            },
        }
    ]

    candidates_data = [
        {
            "id": "POINT_CANDIDATE",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.567752052053379, 44.83814660030956],
                "type": "Point",
            },
        }
    ]

    def test_result(self):
        # Before inspection we have only one building
        self.assertEqual(Building.objects.all().count(), 1)
        b = Building.objects.all().first()
        shape = b.shape.clone()
        point = b.point.clone()

        i = Inspector()
        i.inspect()

        # After inspection we still have only one building
        self.assertEqual(Building.objects.all().count(), 1)

        b.refresh_from_db()
        self.assertIsInstance(b.shape, Polygon)
        self.assertEqual(shape.equals(b.shape), True)
        self.assertEqual(point.equals(b.point), True)


class TestPolyCandidateOnPointBdg(InspectTest):
    bdgs_data = [
        {
            "id": "POINT_BDG",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.567752052053379, 44.83814660030956],
                "type": "Point",
            },
        }
    ]

    candidates_data = [
        {
            "id": "POLY_CANDIDATE",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [-0.567884072259659, 44.83820534369249],
                        [-0.567884072259659, 44.838091952624836],
                        [-0.5676364726049883, 44.838091952624836],
                        [-0.5676364726049883, 44.83820534369249],
                        [-0.567884072259659, 44.83820534369249],
                    ]
                ],
                "type": "Polygon",
            },
        }
    ]

    def test_result(self):
        # Before inspection we have only one building with a point shape
        b = Building.objects.all().first()
        self.assertIsInstance(b.shape, Point)

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        # Check the building is now a polygon
        b.refresh_from_db()
        self.assertIsInstance(b.shape, Polygon)


class TestPointCandidateOutsidePolyBdg(InspectTest):
    bdgs_data = [
        {
            "id": "POLY_BDG",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [-0.567884072259659, 44.83820534369249],
                        [-0.567884072259659, 44.838091952624836],
                        [-0.5676364726049883, 44.838091952624836],
                        [-0.5676364726049883, 44.83820534369249],
                        [-0.567884072259659, 44.83820534369249],
                    ]
                ],
                "type": "Polygon",
            },
        }
    ]

    candidates_data = [
        {
            "id": "POINT_BDG",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.5677886432262085, 44.83825929581545],
                "type": "Point",
            },
        }
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 2)

        b_poly = Building.objects.get(ext_ids__contains=[{"id": "POLY_BDG"}])
        self.assertEqual(b_poly.shape.geom_type, "Polygon")

        b_point = Building.objects.get(ext_ids__contains=[{"id": "POINT_BDG"}])
        self.assertEqual(b_point.shape.geom_type, "Point")


class TestOnePolyCandidatesOnTwoPointBdgs(InspectTest):
    bdgs_data = [
        {
            "id": "FIRST_BDG",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.5739328733325522, 44.84786070152114],
                "type": "Point",
            },
        },
        {
            "id": "SECOND_BDG",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.573884455423979, 44.847787256761166],
                "type": "Point",
            },
        },
    ]

    candidates_data = [
        {
            "id": "POLY_BDG",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [-0.5739986747433647, 44.847888277336494],
                        [-0.573975794455265, 44.84774228183113],
                        [-0.5738054634203138, 44.84775670115647],
                        [-0.5738372415973458, 44.84790359783108],
                        [-0.5739986747433647, 44.847888277336494],
                    ]
                ],
                "type": "Polygon",
            },
        }
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 2)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "toomany_geomatches")


class TestBdgAndCandidateWithSamePoint(InspectTest):
    bdgs_data = [
        {
            "id": "POINT_BDG",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.5738844554153957, 44.847736563832484],
                "type": "Point",
            },
        }
    ]

    candidates_data = [
        {
            "id": "POINT_CANDIDATE",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [-0.5738844554153957, 44.847736563832484],
                "type": "Point",
            },
        }
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "update")


class TestUpdatePointBdgAndTouchingPolyBdgsWithOnePolyCandidate(InspectTest):
    bdgs_data = [
        {
            "id": "west",
            "source": "dummy",
            "geometry": {
                "coordinates": [
                    [
                        [-0.5740296355767782, 44.8478672054716],
                        [-0.5740268205823043, 44.8477602315628],
                        [-0.5739733356839452, 44.847737878781004],
                        [-0.5739097168035983, 44.84781331938575],
                        [-0.5739547567185639, 44.84786800378342],
                        [-0.5740296355767782, 44.8478672054716],
                    ]
                ],
                "type": "Polygon",
            },
        },
        {
            "id": "east",
            "source": "dummy",
            "geometry": {
                "coordinates": [
                    [
                        [-0.5737470101107363, 44.847866008003564],
                        [-0.5737988060129169, 44.8478117227601],
                        [-0.5737087261829572, 44.84771313104778],
                        [-0.5736850802278184, 44.84782489491971],
                        [-0.5736923992141101, 44.84788556664486],
                        [-0.5737470101107363, 44.847866008003564],
                    ]
                ],
                "type": "Polygon",
            },
        },
        {
            "id": "central",
            "source": "dummy",
            "geometry": {
                "coordinates": [-0.5738567949043727, 44.84781252107311],
                "type": "Point",
            },
        },
    ]

    candidates_data = [
        {
            "id": "MATCH_ON_POINT",
            "source": "dummy2",
            "geometry": {
                "coordinates": [
                    [
                        [-0.5738719958749243, 44.8478699995637],
                        [-0.57391703578989, 44.8478672054716],
                        [-0.57391703578989, 44.847768214697396],
                        [-0.573835400944489, 44.84772191250278],
                        [-0.5737807900478913, 44.84773628215328],
                        [-0.573795428019281, 44.84787598690309],
                        [-0.5738719958749243, 44.8478699995637],
                    ]
                ],
                "type": "Polygon",
            },
        }
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 3)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "update")

        # Check the central building is now a polygon
        b = Building.objects.get(ext_ids__contains=[{"id": "central"}])
        self.assertEqual(b.shape.geom_type, "Polygon")


class TestCandidateOnTwoMatchingBdgs(InspectTest):
    bdgs_data = [
        {
            "id": "POLY_BDG",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [-0.5739986747433647, 44.847888277336494],
                        [-0.573975794455265, 44.84774228183113],
                        [-0.5738054634203138, 44.84775670115647],
                        [-0.5738372415973458, 44.84790359783108],
                        [-0.5739986747433647, 44.847888277336494],
                    ]
                ],
                "type": "Polygon",
            },
        },
        {
            "id": "POINT_BDG",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.5738844554153957, 44.847736563832484],
                "type": "Point",
            },
        },
    ]

    candidates_data = [
        {
            "id": "bigger",
            "source": "bdnb",
            "geometry": {
                "coordinates": [
                    [
                        [-0.5739981812005226, 44.84788784410253],
                        [-0.5739717202509098, 44.84771301356989],
                        [-0.5737983165781486, 44.847730177321466],
                        [-0.5738360375068225, 44.8479038103348],
                        [-0.5739981812005226, 44.84788784410253],
                    ]
                ],
                "type": "Polygon",
            },
        }
    ]

    def test_result(self):
        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 2)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "ambiguous_overlap")


def data_to_candidate(data):
    b_import = BuildingImport.objects.create(
        departement="33",
        import_source="dummy",
        building_created_count=0,
        building_updated_count=0,
        building_refused_count=0,
        candidate_created_count=0,
    )

    for d in data:
        shape = GEOSGeometry(json.dumps(d["geometry"]))
        shape.srid = 4326

        Candidate.objects.create(
            shape=shape,
            source=d["source"],
            source_id=d["id"],
            is_light=False,
            created_by={"source": "import", "id": b_import.id},
        )


def data_to_bdg(data):
    for d in data:
        shape = GEOSGeometry(json.dumps(d["geometry"]))
        shape.srid = 4326

        b = Building.objects.create(
            rnb_id=generate_rnb_id(),
            shape=shape,
            ext_ids=[
                {
                    "source": d["source"],
                    "id": d["id"],
                    "created_at": datetime.now().isoformat(),
                }
            ],
            point=shape.point_on_surface,
        )

        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)
