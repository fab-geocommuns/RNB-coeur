import json
from datetime import datetime
from datetime import timezone
from unittest import mock

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.db import connection
from django.db import transaction
from django.test import TestCase
from django.test import TransactionTestCase

from batid.exceptions import BANUnknownCleInterop
from batid.models import Address
from batid.models import Building
from batid.models import BuildingImport
from batid.models import BuildingWithHistory
from batid.models import Candidate
from batid.services.candidate import _report_count_decisions
from batid.services.candidate import _report_count_refusals
from batid.services.candidate import _report_list_fake_updates
from batid.services.candidate import Inspector
from batid.services.rnb_id import generate_rnb_id
from batid.tests.helpers import coords_to_mp_geom
from batid.tests.helpers import coords_to_point_geom
from batid.tests.helpers import create_bdg
from batid.tests.helpers import create_paris


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
            created_by={"id": 46, "source": "import"},
        )

        # Create the addresses
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street="rue de Rivoli",
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
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

    def test_creation(self):

        since = datetime.now()

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
        self.assertEqual(len(b.addresses_id), 2)
        addresses_ids = b.addresses_id
        self.assertIn("add_1", addresses_ids)
        self.assertIn("add_2", addresses_ids)

        self.assertEqual(len(b.ext_ids), 1)
        self.assertEqual(b.ext_ids[0]["source"], "bdnb")
        self.assertEqual(b.ext_ids[0]["source_version"], "7.2")
        self.assertEqual(b.ext_ids[0]["id"], "bdnb_1")

        self.assertEqual(b.event_type, "creation")
        self.assertIsNotNone(b.event_id)

        # check the candidate inspection_details is set
        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "creation")
        self.assertEqual(candidate.inspection_details["rnb_id"], b.rnb_id)

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"creation": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {})

        too_late = datetime.now()
        decision_counts = _report_count_decisions(too_late)
        self.assertDictEqual(decision_counts, {})


class TestInvalidGeom(TestCase):
    def setUp(self):

        # One very big building (should be refused)
        too_big_coords = [
            [2.517814533112869, 50.494009514528585],
            [2.517814533112869, 50.467950398015915],
            [2.574133107473557, 50.467950398015915],
            [2.574133107473557, 50.494009514528585],
            [2.517814533112869, 50.494009514528585],
        ]
        Candidate.objects.create(
            shape=coords_to_mp_geom(too_big_coords),
            source="dummy",
            source_version="1.0.1",
            source_id="too_big",
            address_keys=[],
            is_light=False,
            created_by={"id": 46, "source": "import"},
        )

        # Too small
        too_small_coords = [
            [1.3700879356348707, 46.13019858165205],
            [1.3700879356348707, 46.1301961444135],
            [1.3700925345636392, 46.1301961444135],
            [1.3700925345636392, 46.13019858165205],
            [1.3700879356348707, 46.13019858165205],
        ]
        Candidate.objects.create(
            shape=coords_to_mp_geom(too_small_coords),
            source="dummy",
            source_version="1.0.1",
            source_id="too_small",
            address_keys=[],
            is_light=False,
            created_by={"id": 46, "source": "import"},
        )

        # Invalid point
        invalid_geom = "POINT(200 200)"
        Candidate.objects.create(
            shape=GEOSGeometry(invalid_geom),
            source="dummy",
            source_version="1.0.1",
            source_id="invalid_coords",
            address_keys=[],
            is_light=False,
            created_by={"id": 46, "source": "import"},
        )

    def test(self):

        i = Inspector()
        i.inspect()

        c = Candidate.objects.get(source_id="too_big")
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "area_too_large")

        c = Candidate.objects.get(source_id="too_small")
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "area_too_small")

        c = Candidate.objects.get(source_id="invalid_coords")
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "invalid_geometry")

        bdg_count = Building.objects.all().count()
        self.assertEqual(bdg_count, 0)


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
        b = create_bdg("EXISTING", coords)
        b.ext_ids = Building.add_ext_id(
            b.ext_ids, "bdnb", "7.2", "bdnb_previous", datetime.now().isoformat()
        )
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
            street="rue de Rivoli",
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
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_3",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

    def test_merge(self):

        since = datetime.now()

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
        self.assertEqual(len(b.addresses_id), 3)

        addresses_ids = b.addresses_id
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

        self.assertEqual(b.event_type, "update")
        self.assertIsNotNone(b.event_id)

        # Check the candidate inspection_details is set
        first_candidate = Candidate.objects.all().order_by("inspected_at").first()
        second_candidate = Candidate.objects.all().order_by("inspected_at").last()

        self.assertEqual(first_candidate.inspection_details["decision"], "update")
        self.assertEqual(first_candidate.inspection_details["rnb_id"], b.rnb_id)

        self.assertEqual(second_candidate.inspection_details["decision"], "update")
        self.assertEqual(second_candidate.inspection_details["rnb_id"], b.rnb_id)

        # Test reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"update": 2})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])


class InspectorMergeBuilding(TestCase):
    def test_empty_incoming_address(self):
        # Create an address
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

        # we create a building
        shape = coords_to_mp_geom(
            [
                [2.349804906833981, 48.85789205519228],
                [2.349701279442314, 48.85786369735885],
                [2.3496535925009994, 48.85777922711969],
                [2.349861764341199, 48.85773095834841],
                [2.3499452164882086, 48.857847406681174],
                [2.349804906833981, 48.85789205519228],
            ]
        )

        b = Building.create_new(
            user=None,
            event_origin={"source": "import"},
            status="constructed",
            addresses_id=["add_1"],
            shape=shape,
            ext_ids=[
                {
                    "id": "bdtopo_1",
                    "source": "bdtopo",
                    "created_at": "2023-12-10T19:42:40.038998+00:00",
                    "source_version": "2023_01",
                }
            ],
        )
        rnb_id = b.rnb_id

        c = Candidate.objects.create(
            shape=shape,
            source="bdtopo",
            source_id="bdtopo_1",
            source_version="2023_01",
            # typical case : empty address incoming from the BDTOPO
            address_keys=None,
            is_light=False,
        )

        # we expect the candidate to be refused, because it contains no new information about the building.
        since = datetime.now()
        i = Inspector()
        i.inspect()
        c.refresh_from_db()
        self.assertTrue(
            c.inspection_details
            == {"decision": "refusal", "reason": "nothing_to_update"}
        )

        # the building has not been updated (no new entry in the BuildingWithHistory view)
        buildings = BuildingWithHistory.objects.filter(rnb_id=rnb_id).all()
        self.assertEqual(len(buildings), 1)
        building = buildings[0]
        self.assertEqual(building.event_type, "creation")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"nothing_to_update": 1})

    def test_all_addresses_are_known(self):
        # Create an address
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

        Address.objects.create(
            id="add_2",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="40",
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

        Address.objects.create(
            id="add_3",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="40",
            street="rue de Rivoli",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

        # we create a building
        shape = coords_to_mp_geom(
            [
                [2.349804906833981, 48.85789205519228],
                [2.349701279442314, 48.85786369735885],
                [2.3496535925009994, 48.85777922711969],
                [2.349861764341199, 48.85773095834841],
                [2.3499452164882086, 48.857847406681174],
                [2.349804906833981, 48.85789205519228],
            ]
        )

        b = Building.create_new(
            user=None,
            event_origin={"source": "import"},
            status="constructed",
            addresses_id=["add_1", "add_2", "add_3"],
            shape=shape,
            ext_ids=[
                {
                    "id": "bdtopo_1",
                    "source": "bdtopo",
                    "created_at": "2023-12-10T19:42:40.038998+00:00",
                    "source_version": "2023_01",
                }
            ],
        )
        rnb_id = b.rnb_id

        c = Candidate.objects.create(
            shape=shape,
            source="bdtopo",
            source_id="bdtopo_1",
            source_version="2023_01",
            # candidate contains only addresses already associated to the building
            address_keys=["add_3", "add_1"],
            is_light=False,
        )

        # we expect the candidate to be refused, because it contains no new information about the building.
        i = Inspector()
        i.inspect()
        c.refresh_from_db()
        self.assertTrue(
            c.inspection_details
            == {"decision": "refusal", "reason": "nothing_to_update"}
        )

        # the building has not been updated (no new entry in the BuildingWithHistory view)
        buildings = BuildingWithHistory.objects.filter(rnb_id=rnb_id).all()
        self.assertEqual(len(buildings), 1)
        building = buildings[0]
        self.assertEqual(building.event_type, "creation")


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")
        self.assertEqual(candidate.inspection_details["reason"], "ambiguous_overlap")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"ambiguous_overlap": 1})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"update": 1})


class TestOneSmallBdgThenOneBigCand(InspectTest):
    bdgs_data = [OneSmallOneBig.small]
    candidates_data = [OneSmallOneBig.big]

    def test_result(self):

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")
        self.assertEqual(candidate.inspection_details["reason"], "ambiguous_overlap")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"ambiguous_overlap": 1})


class TestOneBigBdgThenOneSmallCand(InspectTest):
    bdgs_data = [OneSmallOneBig.big]
    candidates_data = [OneSmallOneBig.small]

    def test_result(self):

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"ambiguous_overlap": 1})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        candidate = Candidate.objects.all().order_by("inspected_at").first()
        self.assertEqual(candidate.inspection_details["decision"], "refusal")
        self.assertEqual(candidate.inspection_details["reason"], "ambiguous_overlap")

        candidate_2 = Candidate.objects.all().order_by("inspected_at").last()
        self.assertEqual(candidate_2.inspection_details["decision"], "refusal")
        self.assertEqual(candidate_2.inspection_details["reason"], "ambiguous_overlap")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 2})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"ambiguous_overlap": 2})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        # After inspection we still have only one building
        self.assertEqual(Building.objects.all().count(), 1)

        b.refresh_from_db()
        self.assertIsInstance(b.shape, Polygon)
        self.assertEqual(shape.equals(b.shape), True)
        self.assertEqual(point.equals(b.point), True)

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"update": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        # Check the building is now a polygon
        b.refresh_from_db()
        self.assertIsInstance(b.shape, Polygon)

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"update": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 2)

        b_poly = Building.objects.get(ext_ids__contains=[{"id": "POLY_BDG"}])
        self.assertEqual(b_poly.shape.geom_type, "Polygon")

        b_point = Building.objects.get(ext_ids__contains=[{"id": "POINT_BDG"}])
        self.assertEqual(b_point.shape.geom_type, "Point")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"creation": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 2)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "too_many_geomatches")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"too_many_geomatches": 1})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 1)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "update")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"update": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 3)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "update")

        # Check the central building is now a polygon
        b = Building.objects.get(ext_ids__contains=[{"id": "central"}])
        self.assertEqual(b.shape.geom_type, "Polygon")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"update": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {})


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

        since = datetime.now()

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.all().count(), 2)

        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "ambiguous_overlap")

        # Test the reports
        decision_counts = _report_count_decisions(since)
        self.assertDictEqual(decision_counts, {"refusal": 1})

        fake_updates = _report_list_fake_updates(since)
        self.assertListEqual(fake_updates, [])

        refusals_counts = _report_count_refusals(since)
        self.assertDictEqual(refusals_counts, {"ambiguous_overlap": 1})

    def test_fake_update(self):
        # we create a building
        rnb_id = "xxxxyyyyzzzz"
        building = Building.objects.create(
            rnb_id=rnb_id,
            shape="POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
            status="constructed",
        )

        # we save a second time the building but make no change to create a "fake update"
        building.save()

        # we create by hand an inspected candidate
        now = datetime.now(timezone.utc)
        candidat = Candidate.objects.create(
            inspected_at=datetime.now(timezone.utc),
            inspection_details={"decision": "update", "rnb_id": rnb_id},
        )

        # rnb_id should be listed as a fake update
        fake_updates = _report_list_fake_updates(now)
        self.assertListEqual(fake_updates, [rnb_id])


class TestCandidateCLoseToPointBdg(InspectTest):
    """
    Some buildings have only a Point in the shape attribute.
    BD Topo (and others) can help us to transform this point into a polygon.
    The problem is sometimes the candidate does not intersect the building.
    We have to attach the candidate to the building if it is close enough.
    We verify the inspection attaches candidate polygon and building point when they are close enough.


    POINT_BDG is a building with a point shape.
    It is close to the candidate. Its shape must be updated with the candidate polygon.

    FAR_POINT_BDG is a building with a point shape.
    It is far from the candidate and should be ignored.

    POLY_BDG_NEIGHBOR is a building with a polygon shape.
    It intersects the candidate but not enough. It should be ignored

    """

    bdgs_data = [
        {
            "id": "POINT_BDG",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [-0.4054973749373687, 42.13386683679241],
                "type": "Point",
            },
        },
        {
            "id": "FAR_POINT_BDG",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [-0.40521491170318313, 42.13399847871867],
                "type": "Point",
            },
        },
        {
            "id": "POLY_BDG_NEIGHBOR",
            "source": "bdtopo",
            "geometry": {
                "coordinates": [
                    [
                        [-0.4054742368722941, 42.134111441961494],
                        [-0.4054853481118812, 42.133891163317315],
                        [-0.4052423823313802, 42.133890613993145],
                        [-0.40526386406216375, 42.13413561214],
                        [-0.4054742368722941, 42.134111441961494],
                    ]
                ],
                "type": "Polygon",
            },
        },
    ]

    candidates_data = [
        {
            "id": "CDT_POLY",
            "source": "bdnb",
            "geometry": {
                "coordinates": [
                    [
                        [-0.4055384428695845, 42.1338676176932],
                        [-0.4054805265556638, 42.13390978632495],
                        [-0.40546683724414834, 42.1341050111069],
                        [-0.4059112133287499, 42.13408705045228],
                        [-0.40588488773067866, 42.13384575246573],
                        [-0.4055384428695845, 42.1338676176932],
                    ]
                ],
                "type": "Polygon",
            },
        },
    ]

    def test_result(self):

        i = Inspector()
        i.inspect()

        # The candidate updated a building
        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "update")

        # Updated building now has a polygon
        rnb_id = c.inspection_details["rnb_id"]
        bdg = Building.objects.get(rnb_id=rnb_id)

        self.assertEqual(bdg.shape.geom_type, "Polygon")
        self.assertEqual(len(bdg.ext_ids), 2)
        self.assertEqual(bdg.ext_ids[1]["id"], "CDT_POLY")


class TestCandidateCLoseToAmbiguousPointsBdgs(InspectTest):
    bdgs_data = [
        {
            "id": "CLOSE_ONE",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.40526639833487366, 42.13435554467577],
                "type": "Point",
            },
        },
        {
            "id": "CLOSE_TWO",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.4054133335975223, 42.134342572850386],
                "type": "Point",
            },
        },
        {
            "id": "INSIDE",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.4052891383165331, 42.134270579167264],
                "type": "Point",
            },
        },
        {
            "id": "FAR",
            "source": "bdnb",
            "geometry": {
                "coordinates": [-0.40496020881957406, 42.13401039632299],
                "type": "Point",
            },
        },
    ]

    candidates_data = [
        {
            "id": "AMBIGUOUS_POLY",
            "source": "bdnb",
            "geometry": {
                "coordinates": [
                    [
                        [-0.40533767926592645, 42.134363059816536],
                        [-0.4054953663784602, 42.134262535288656],
                        [-0.4052270216421334, 42.13414867568085],
                        [-0.40517030961083833, 42.13431484909324],
                        [-0.40533767926592645, 42.134363059816536],
                    ]
                ],
                "type": "Polygon",
            },
        },
    ]

    def test_result(self):

        i = Inspector()
        i.inspect()

        # The candidate has been refused
        c = Candidate.objects.all().first()
        self.assertEqual(c.inspection_details["decision"], "refusal")
        self.assertEqual(c.inspection_details["reason"], "too_many_geomatches")
        # There are 4 bdgs in the database but one is too far from the candidate
        self.assertEqual(len(c.inspection_details["matches"]), 3)

        # The buildings have not been updated
        bdgs = Building.objects.all()
        self.assertEqual(len(bdgs), 4)

        for bdg in bdgs:

            self.assertEqual(bdg.shape.geom_type, "Point")
            self.assertEqual(len(bdg.ext_ids), 1)

            history_rows = (
                BuildingWithHistory.objects.filter(rnb_id=bdg.rnb_id).all().count()
            )
            self.assertEqual(history_rows, 1)


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
            status="constructed",
        )


# we need to use TransactionTestCase because we are testing thez proper rollback of the transactions during the inspection
class NonExistingAddress(TransactionTestCase):
    @mock.patch("batid.models.requests.get")
    def test_non_existing_address_raises(self, get_mock):
        """
        When an address is not found in the database, an error is raised
        """
        get_mock.return_value.status_code = 404
        get_mock.return_value.json.return_value = {
            "details": "what is this id?",
        }

        coords = [
            [2.349804906833981, 48.85789205519228],
            [2.349701279442314, 48.85786369735885],
            [2.3496535925009994, 48.85777922711969],
            [2.349861764341199, 48.85773095834841],
            [2.3499452164882086, 48.857847406681174],
            [2.349804906833981, 48.85789205519228],
        ]
        candidate = Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdnb",
            source_version="7.2",
            source_id="bdnb_1",
            address_keys=["add_1"],
            is_light=False,
            created_by={"id": 1, "source": "import"},
        )

        i = Inspector()
        with self.assertRaises(BANUnknownCleInterop):
            i.inspect()

        candidate.refresh_from_db()
        # check the candidate inspection_details is properly reverted
        self.assertFalse(candidate.inspection_details)
        self.assertFalse(candidate.inspected_at)

        # no building should have been created
        self.assertEqual(Building.objects.all().count(), 0)

    @mock.patch("batid.models.requests.get")
    def test_non_existing_address_raises_during_update(self, get_mock):
        # a non existing address will be checked on the BAN API.
        # if the BAN API doesn't know it, the inspection will crash.

        get_mock.return_value.status_code = 404
        get_mock.return_value.json.return_value = {
            "details": "what is this id?",
        }

        shape = coords_to_mp_geom(
            [
                [2.349804906833981, 48.85789205519228],
                [2.349701279442314, 48.85786369735885],
                [2.3496535925009994, 48.85777922711969],
                [2.349861764341199, 48.85773095834841],
                [2.3499452164882086, 48.857847406681174],
                [2.349804906833981, 48.85789205519228],
            ]
        )

        Building.objects.create(rnb_id=generate_rnb_id(), shape=shape)

        # this candidate has the same shape, it will yield an update
        candidate = Candidate.objects.create(
            shape=shape,
            source="bdnb",
            source_version="7.2",
            source_id="bdnb_1",
            address_keys=["add_1"],
            is_light=False,
        )

        i = Inspector()
        with self.assertRaises(BANUnknownCleInterop) as exinfo:
            i.inspect()
            # check handle_bdgs_updates is in the stacktrace
            # ie the candidate was supposed to update a building
            self.assertTrue("handle_bdgs_updates" in str(exinfo.value))

        candidate.refresh_from_db()
        # check the candidate inspection_details is properly reverted
        self.assertFalse(candidate.inspection_details)
        self.assertFalse(candidate.inspected_at)


class GeosIntersectsBugInterception(TransactionTestCase):

    WKT_1 = "POLYGON ((1.839012980156925 43.169860517728324, 1.838983490127865 43.169860200336274, 1.838898525601717 43.169868281549725, 1.838918565176068 43.1699719478626, 1.838920733577112 43.16998636433192, 1.838978629555589 43.16997979090823, 1.838982586839382 43.169966339940714, 1.838974943184281 43.169918580432174, 1.839020497362873 43.169914572864634, 1.839012980156925 43.169860517728324))"
    WKT_2 = "POLYGON ((1.8391355300979277 43.16987802887805, 1.83913336164737 43.16986361241434, 1.8390129801569248 43.169860517728324, 1.8390790978572837 43.16987292371998, 1.8390909520103162 43.16995581178317, 1.8391377530291442 43.16995091801345, 1.8391293863398452 43.16987796276235, 1.8391355300979277 43.16987802887805))"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buggy_geos = False

    def setUp(self):
        """
        We do not have full control over GEOS version (our production db is managed)
        The bug appears on GEOS 3.11 but not on GEOS 3.9 and seems to be fixed on 3.12
        We first have to check if the bug is present, then we can test the interception
        """
        with transaction.atomic():
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        "SELECT ST_Intersects(ST_GeomFromText(%s), ST_GeomFromText(%s))",
                        [self.WKT_1, self.WKT_2],
                    )
                    cursor.fetchone()
                except Exception as e:
                    if "TopologyException: side location conflict" in str(e):
                        self.buggy_geos = True

    def test_interception(self):

        if self.buggy_geos:

            print("GEOS is buggy, we do the skip test")

            bdg_geom = GEOSGeometry(self.WKT_1)
            Building.objects.create(
                rnb_id="BUGGY", shape=bdg_geom, point=bdg_geom.point_on_surface
            )

            candidate_geom = GEOSGeometry(self.WKT_2)
            Candidate.objects.create(
                shape=candidate_geom,
                is_light=False,
            )

            since = datetime.now()

            i = Inspector()
            i.inspect()

            c = Candidate.objects.all().first()
            self.assertEqual(c.inspection_details["decision"], "refusal")
            self.assertEqual(c.inspection_details["reason"], "topology_exception")
            self.assertNotEqual(c.inspected_at, None)

            # Test the reports
            decision_counts = _report_count_decisions(since)
            self.assertDictEqual(decision_counts, {"refusal": 1})

            fake_updates = _report_list_fake_updates(since)
            self.assertListEqual(fake_updates, [])

            refusals_counts = _report_count_refusals(since)
            self.assertDictEqual(refusals_counts, {"topology_exception": 1})
