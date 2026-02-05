import json
import uuid
from unittest.mock import patch

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.test import TransactionTestCase
from nanoid import generate

import batid.tests.helpers as helpers
from batid.exceptions import BANUnknownCleInterop
from batid.models import Address
from batid.models import Building
from batid.models import BuildingImport
from batid.models import Plot
from batid.services.imports.import_bal import create_dpt_bal_rnb_links
from batid.services.imports.import_bal import find_bdg_to_link
from batid.services.rnb_id import generate_rnb_id


class BALImport(TransactionTestCase):
    def setUp(self):

        # Building ONE

        Address.objects.create(
            id="OLD_ON_ONE",
            source="Import BAN",
            point=Point(
                0,
                0,
            ),
        )

        Address.objects.create(
            id="GO_ON_ONE",
            source="Import BAN",
            point=Point(
                0,
                0,
            ),
        )

        b_one = Building.objects.create(
            rnb_id="ONE",
            addresses_id=["OLD_ON_ONE"],
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.520396681614983, 44.83160353126539],
                                [-0.5203518277556043, 44.83151793460064],
                                [-0.5201764899430827, 44.83157287842056],
                                [-0.5202327611480939, 44.831651534744594],
                                [-0.520396681614983, 44.83160353126539],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        # Building TWO
        Building.objects.create(
            rnb_id="TWO",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5204219628803344, 44.83158791566697],
                                [-0.5205932230694259, 44.83153008008131],
                                [-0.5205369518644432, 44.831448531806274],
                                [-0.5203705848234677, 44.83151272939409],
                                [-0.5204219628803344, 44.83158791566697],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        Address.objects.create(
            id="GO_ON_TWO",
            source="Import BAN",
            point=Point(
                0,
                0,
            ),
        )

    @patch("batid.services.imports.import_bal.Source.find")
    def test_bal_import(self, source_mock):

        source_mock.return_value = helpers.copy_fixture(
            "bal_import_test_data.csv", "bal_import_test_data_COPY.csv"
        )

        old_updated_at = Building.objects.get(rnb_id="ONE").updated_at

        # We execute the BAL import
        bulk_launch_uuid = uuid.uuid4()

        create_dpt_bal_rnb_links({"dpt": "01"}, bulk_launch_uuid)

        # We check the import result
        report = BuildingImport.objects.get(bulk_launch_uuid=bulk_launch_uuid)
        self.assertEqual(report.import_source, "bal")
        self.assertEqual(report.bulk_launch_uuid, bulk_launch_uuid)
        self.assertEqual(report.departement, "01")
        self.assertEqual(report.building_updated_count, 2)
        self.assertEqual(report.building_refused_count, 0)

        # We check the buildings
        bdg_one = Building.objects.get(rnb_id="ONE")
        new_updated_at = bdg_one.updated_at

        self.assertListEqual(bdg_one.addresses_id, ["OLD_ON_ONE", "GO_ON_ONE"])
        self.assertDictEqual(
            bdg_one.event_origin, {"source": "import", "id": report.id}
        )

        # We check the updated_at field has changed automatically
        self.assertNotEqual(old_updated_at, new_updated_at)

        bdg_two = Building.objects.get(rnb_id="TWO")
        self.assertListEqual(bdg_two.addresses_id, ["GO_ON_TWO"])
        self.assertDictEqual(
            bdg_two.event_origin, {"source": "import", "id": report.id}
        )


class BALImportWithUnknownCleInterop(TestCase):
    @patch("batid.models.Address.add_new_address_from_ban_api")
    @patch("batid.services.imports.import_bal.Source.find")
    def test_bal_import(self, source_mock, new_address_mock):

        source_mock.return_value = helpers.copy_fixture(
            "bal_import_test_data.csv", "bal_import_test_data_COPY.csv"
        )

        new_address_mock.side_effect = BANUnknownCleInterop()

        # One of the CSV address should be linked to this building but its CLE_INTEROP is unknown
        Building.objects.create(
            rnb_id="NO_ADDRESS",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5208465518688001, 44.83137629535605],
                                [-0.5209714266673586, 44.83124373127637],
                                [-0.5209000696392536, 44.83120522712949],
                                [-0.5207868291392401, 44.831261883222226],
                                [-0.5208209564132744, 44.83129653692134],
                                [-0.5207542531047125, 44.83133284077405],
                                [-0.5208465518688001, 44.83137629535605],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        # We execute the BAL import
        bulk_launch_uuid = uuid.uuid4()
        create_dpt_bal_rnb_links({"dpt": "01"}, bulk_launch_uuid)

        # self.assertEqual(new_address_mock.call_count, 1)

        report = BuildingImport.objects.get(bulk_launch_uuid=bulk_launch_uuid)
        self.assertEqual(report.import_source, "bal")
        self.assertEqual(report.bulk_launch_uuid, bulk_launch_uuid)
        self.assertEqual(report.departement, "01")
        self.assertEqual(report.building_updated_count, 0)
        self.assertEqual(report.building_refused_count, 1)


class LinkSearch(TestCase):
    """
    This class is dedidated to the tests of the search of the building to link
    to the address in the BAL import.
    """

    def test_address_on_real_bdg(self):

        # Isolated real building, no address in history
        Building.objects.create(
            rnb_id="ISOLATED",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5198583223793491, 44.830338092701794],
                                [-0.5199975213340906, 44.83029578430569],
                                [-0.5199149197562463, 44.83018079209748],
                                [-0.5198124326153959, 44.8302144219181],
                                [-0.5198736189686883, 44.83030446295385],
                                [-0.5198414961325852, 44.830316396092286],
                                [-0.5198583223793491, 44.830338092701794],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        # The point is on the building
        address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5198996231682713, 44.83025130621479],
                    "type": "Point",
                }
            )
        )

        bdg = find_bdg_to_link(address_point, "_")
        self.assertEqual(bdg.rnb_id, "ISOLATED")

    def test_address_on_inactive_bdg(self):

        # Inactive building, no address in history
        Building.objects.create(
            rnb_id="INACTIVE",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5198583223793491, 44.830338092701794],
                                [-0.5199975213340906, 44.83029578430569],
                                [-0.5199149197562463, 44.83018079209748],
                                [-0.5198124326153959, 44.8302144219181],
                                [-0.5198736189686883, 44.83030446295385],
                                [-0.5198414961325852, 44.830316396092286],
                                [-0.5198583223793491, 44.830338092701794],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
            is_active=False,
        )

        # The point is on the building
        address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5198996231682713, 44.83025130621479],
                    "type": "Point",
                }
            )
        )

        bdg = find_bdg_to_link(address_point, "_")
        self.assertEqual(bdg, None)

    def test_address_on_demolished_bdg(self):

        # Isolated demolished building, no address in history
        Building.objects.create(
            rnb_id="DEMOLISHED",
            status="demolished",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5198583223793491, 44.830338092701794],
                                [-0.5199975213340906, 44.83029578430569],
                                [-0.5199149197562463, 44.83018079209748],
                                [-0.5198124326153959, 44.8302144219181],
                                [-0.5198736189686883, 44.83030446295385],
                                [-0.5198414961325852, 44.830316396092286],
                                [-0.5198583223793491, 44.830338092701794],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        # The point is on the building
        address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5198996231682713, 44.83025130621479],
                    "type": "Point",
                }
            )
        )

        bdg = find_bdg_to_link(address_point, "_")
        self.assertIsNone(bdg)

    def test_address_close_to_bdg(self):

        # An isolated building and an address point close to it (but not directly on it)
        Building.objects.create(
            rnb_id="CLOSE",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5206731809492453, 44.83095412267062],
                                [-0.5207117887700861, 44.8308267825044],
                                [-0.5205996422437806, 44.83081157120293],
                                [-0.5205647113583325, 44.83094369208712],
                                [-0.5206731809492453, 44.83095412267062],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        # This address point is close to the building
        # It should not match
        close_address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5205800319222078, 44.83085807431161],
                    "type": "Point",
                }
            )
        )

        bdg = find_bdg_to_link(close_address_point, "_")
        # self.assertEqual(bdg.rnb_id, "CLOSE")
        self.assertIsNone(bdg)

        # This address point is close (4 meters) but not enough
        # It should not match
        a_bit_too_far_address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5205249836429005, 44.83085305399297],
                    "type": "Point",
                }
            )
        )
        bdg = find_bdg_to_link(a_bit_too_far_address_point, "_")
        self.assertEqual(bdg, None)

        # This address point is far (8 meters) from the building
        # It should not match
        far_address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5204703366846388, 44.83085057731668],
                    "type": "Point",
                }
            )
        )

        bdg = find_bdg_to_link(far_address_point, "_")
        self.assertEqual(bdg, None)

    def test_point_ambiguous_point(self):

        # Two buildings close to each other ...
        Building.objects.create(
            rnb_id="AMBIGUOUS_1",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5203385798371869, 44.83090544659947],
                                [-0.5203048745971444, 44.83085503205342],
                                [-0.5203152925802499, 44.83085329362015],
                                [-0.520268718066319, 44.83078114858796],
                                [-0.5201847613769814, 44.83080505207232],
                                [-0.5200781302537791, 44.830845036060765],
                                [-0.5202092742793241, 44.83095412267062],
                                [-0.5203385798371869, 44.83090544659947],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        Building.objects.create(
            rnb_id="AMBIGUOUS_2",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5202006947631901, 44.83079549067966],
                                [-0.5203140669348727, 44.830758114311436],
                                [-0.5202245948431994, 44.830637292862434],
                                [-0.5201289945253791, 44.83066988860176],
                                [-0.5202006947631901, 44.83079549067966],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )

        # ... and an adress point close to both
        address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5202846514524992, 44.83078071397921],
                    "type": "Point",
                }
            )
        )

        # The point is very close to the two buildings
        # It is not possible to determine which one is the right one
        # We should return None
        bdg = find_bdg_to_link(address_point, "_")

        self.assertEqual(bdg, None)

    def test_address_on_bdg_but_address_in_history(self):
        """
        We do not want to link the address to the building if the address has already been linked to it at any point in time.

        The main scenario is to not attach again the address if someone removed the link (correcting an error).
        We stick to "an import can not undo a contribution" principle

        """

        Address.objects.create(
            id="1234",
            source="Import BAL",
            point=Point(
                0,
                0,
            ),
        )

        # First version of the building has the address
        bdg = Building.objects.create(
            rnb_id="HISTORY",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5206731809492453, 44.83095412267062],
                                [-0.5207117887700861, 44.8308267825044],
                                [-0.5205996422437806, 44.83081157120293],
                                [-0.5205647113583325, 44.83094369208712],
                                [-0.5206731809492453, 44.83095412267062],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
            addresses_id=["1234"],
        )

        # Second version has the address removed
        bdg.addresses_id = []
        bdg.save()

        address_point = Point(-0.5206731809492453, 44.83095412267062, srid=4326)
        address_id = "1234"

        # Since the building had this address in the past, we should not link it
        bdg = find_bdg_to_link(address_point, address_id)
        self.assertIsNone(bdg)

    def test_already_linked_bdg(self):

        Address.objects.create(
            id="1234",
            source="Import BAL",
            point=Point(
                0,
                0,
            ),
        )

        # The building already has the address linked
        bdg = Building.objects.create(
            rnb_id="ALREADY",
            status="constructed",
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5206731809492453, 44.83095412267062],
                                [-0.5207117887700861, 44.8308267825044],
                                [-0.5205996422437806, 44.83081157120293],
                                [-0.5205647113583325, 44.83094369208712],
                                [-0.5206731809492453, 44.83095412267062],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
            addresses_id=["1234"],
        )

        address_point = Point(-0.5206731809492453, 44.83095412267062, srid=4326)
        address_id = "1234"

        # Since the building is already linked to the address, we should not link it again
        bdg = find_bdg_to_link(address_point, address_id)
        self.assertIsNone(bdg)

    def test_address_on_plot(self):
        """
        One building is fully on the plot
        We expect this building to be returned
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [4.336596580524599, 44.140553844425796],
                                [4.336192402642638, 44.13951021813696],
                                [4.337912139939817, 44.13889028971644],
                                [4.338233104728431, 44.1401187654246],
                                [4.336596580524599, 44.140553844425796],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building", "rnb_id": "GOOD"},
                    "geometry": {
                        "coordinates": [
                            [
                                [4.336733090548734, 44.140368534326285],
                                [4.336733090548734, 44.14015863712456],
                                [4.337056911871059, 44.14015863712456],
                                [4.337056911871059, 44.140368534326285],
                                [4.336733090548734, 44.140368534326285],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [4.337658457946446, 44.13921446369753],
                        "type": "Point",
                    },
                    "id": 2,
                },
            ],
        }

        bdg = self._run_geojson_scenario(data)

        self.assertIsNotNone(bdg)
        self.assertEqual(bdg.rnb_id, "GOOD")

    def test_two_buildings_on_plot(self):
        """
        Two buildings are fully covered by the plot.
        We expect None
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7331853542955002, 45.87125206781718],
                                [2.7341582052359854, 45.87101726197966],
                                [2.734407157530427, 45.87124346238235],
                                [2.7344106887536554, 45.87184706893788],
                                [2.7332559787598996, 45.87192943429352],
                                [2.7331853542955002, 45.87125206781718],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7333795706323656, 45.87176839139161],
                                [2.733353086458237, 45.87159013733972],
                                [2.733676193383957, 45.87155202777859],
                                [2.733681490218771, 45.87177699674518],
                                [2.7333795706323656, 45.87176839139161],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.733826270370713, 45.871759786036705],
                                [2.733815676701113, 45.871545881072706],
                                [2.7342429547105667, 45.87150900082332],
                                [2.734209408089953, 45.871764703382524],
                                [2.733826270370713, 45.871759786036705],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 2,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [2.7340469718218685, 45.87120043511055],
                        "type": "Point",
                    },
                    "id": 3,
                },
            ],
        }

        bdg = self._run_geojson_scenario(data)

        self.assertIsNone(bdg)

    def test_ambiguous_second_building_on_plot(self):
        """
        One building is covered by the plot, the other one only intersects it.
        We expect None
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7331853542955002, 45.87125206781718],
                                [2.7341582052359854, 45.87101726197966],
                                [2.734407157530427, 45.87124346238235],
                                [2.7344106887536554, 45.87184706893788],
                                [2.7332559787598996, 45.87192943429352],
                                [2.7331853542955002, 45.87125206781718],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7333795706323656, 45.87176839139161],
                                [2.733353086458237, 45.87159013733972],
                                [2.733676193383957, 45.87155202777859],
                                [2.733681490218771, 45.87177699674518],
                                [2.7333795706323656, 45.87176839139161],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [2.7340469718218685, 45.87120043511055],
                        "type": "Point",
                    },
                    "id": 3,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7341129160415676, 45.87166896108437],
                                [2.7341437242809548, 45.87148407543734],
                                [2.734510489035614, 45.87149020425315],
                                [2.7345280937438474, 45.87168428307166],
                                [2.7341129160415676, 45.87166896108437],
                            ]
                        ],
                        "type": "Polygon",
                    },
                },
            ],
        }

        bdg = self._run_geojson_scenario(data)

        self.assertIsNone(bdg)

    def test_neighbor_touches_the_plot(self):
        """
        One building is covered by the plot, the neighbor building intersects just a little bit the plot.
        Expect the first building to be returned
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7331853542955002, 45.87125206781718],
                                [2.7341582052359854, 45.87101726197966],
                                [2.734407157530427, 45.87124346238235],
                                [2.7344106887536554, 45.87184706893788],
                                [2.7332559787598996, 45.87192943429352],
                                [2.7331853542955002, 45.87125206781718],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building", "rnb_id": "GOOD"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7333795706323656, 45.87176839139161],
                                [2.733353086458237, 45.87159013733972],
                                [2.733676193383957, 45.87155202777859],
                                [2.733681490218771, 45.87177699674518],
                                [2.7333795706323656, 45.87176839139161],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [2.7340469718218685, 45.87120043511055],
                        "type": "Point",
                    },
                    "id": 3,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.734406522806779, 45.871627004232636],
                                [2.7344056862377784, 45.87155419461931],
                                [2.7345115122209336, 45.87154749612964],
                                [2.734518204773252, 45.87163312023583],
                                [2.734406522806779, 45.871627004232636],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 3,
                },
            ],
        }
        bdg = self._run_geojson_scenario(data)
        self.assertIsNotNone(bdg)
        self.assertEqual(bdg.rnb_id, "GOOD")

    def test_ambiguous_plots(self):
        """
        Two plots are neighboring each other.
        - one has building on it
        - the other one is empty
        The address point is on the occupied plot AND very close to the other one.
        We expect None because of this ambiguity
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7331167961568212, 45.87182777699999],
                                [2.733044241045377, 45.871250429332036],
                                [2.7340289178587796, 45.87117104355784],
                                [2.734099745489061, 45.87185544143196],
                                [2.7331167961568212, 45.87182777699999],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7341005953169315, 45.871855740071226],
                                [2.7340303340256185, 45.871170421734234],
                                [2.7349907102394013, 45.87117402326933],
                                [2.7349613989366333, 45.87189432559481],
                                [2.7341005953169315, 45.871855740071226],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7331923768389004, 45.87176227000404],
                                [2.733206170393146, 45.871522169695794],
                                [2.733635494769999, 45.87153537523969],
                                [2.7335613544147463, 45.87176827249843],
                                [2.7331923768389004, 45.87176227000404],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 2,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [2.734027425020031, 45.87117466146867],
                        "type": "Point",
                    },
                    "id": 4,
                },
            ],
        }

        bdg = self._run_geojson_scenario(data)
        self.assertIsNone(bdg)

    def test_bdg_point_on_plot(self):
        """
        Only one building in the plot
        The building is a point
        We expect the building to be returned
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7332569431928846, 45.872036457541896],
                                [2.732778363225435, 45.871415701898314],
                                [2.7341253342617335, 45.870983049925144],
                                [2.7343723432767035, 45.87203108306383],
                                [2.7332569431928846, 45.872036457541896],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building", "rnb_id": "GOOD"},
                    "geometry": {
                        "coordinates": [2.73341518334297, 45.8718214780171],
                        "type": "Point",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [2.7338397300876522, 45.87124102914697],
                        "type": "Point",
                    },
                    "id": 2,
                },
            ],
        }

        bdg = self._run_geojson_scenario(data)

        self.assertIsNotNone(bdg)
        self.assertEqual(bdg.rnb_id, "GOOD")

    def test_two_bdg_points_on_plot(self):
        """
        Two buildings represented as points are in the plot
        We expect None
        """

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [2.7332569431928846, 45.872036457541896],
                                [2.732778363225435, 45.871415701898314],
                                [2.7341253342617335, 45.870983049925144],
                                [2.7343723432767035, 45.87203108306383],
                                [2.7332569431928846, 45.872036457541896],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [2.73341518334297, 45.8718214780171],
                        "type": "Point",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": {
                        "coordinates": [2.7338397300876522, 45.87124102914697],
                        "type": "Point",
                    },
                    "id": 2,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building"},
                    "geometry": {
                        "coordinates": [2.7337316636432263, 45.8718214780171],
                        "type": "Point",
                    },
                    "id": 3,
                },
            ],
        }

        bdg = self._run_geojson_scenario(data)
        self.assertIsNone(bdg)

    def test_bdg_on_plot_with_address(self):
        """
        One building is fully on the plot
        Initially this building has no adress : it should be returned
        Then, we add the address to building and run again : it should return None
        Finally, we remove the address from the building. Since the address has been in the history, it should return None
        """

        address_point = {
            "coordinates": [4.337658457946446, 44.13921446369753],
            "type": "Point",
        }

        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"type": "plot"},
                    "geometry": {
                        "coordinates": [
                            [
                                [4.336596580524599, 44.140553844425796],
                                [4.336192402642638, 44.13951021813696],
                                [4.337912139939817, 44.13889028971644],
                                [4.338233104728431, 44.1401187654246],
                                [4.336596580524599, 44.140553844425796],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 0,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "building", "rnb_id": "GOOD"},
                    "geometry": {
                        "coordinates": [
                            [
                                [4.336733090548734, 44.140368534326285],
                                [4.336733090548734, 44.14015863712456],
                                [4.337056911871059, 44.14015863712456],
                                [4.337056911871059, 44.140368534326285],
                                [4.336733090548734, 44.140368534326285],
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "id": 1,
                },
                {
                    "type": "Feature",
                    "properties": {"type": "address"},
                    "geometry": address_point,
                    "id": 2,
                },
            ],
        }
        # We create the address in advance
        Address.objects.create(id="DUMMY")

        # First run : building has no address yet
        bdg = self._run_geojson_scenario(data)
        self.assertIsNotNone(bdg)
        self.assertEqual(bdg.rnb_id, "GOOD")

        # Second run : building has now the address linked
        bdg = Building.objects.get(rnb_id="GOOD")
        bdg.addresses_id = ["DUMMY"]
        bdg.save()

        bdg = find_bdg_to_link(GEOSGeometry(json.dumps(address_point)), "DUMMY")
        self.assertIsNone(bdg)

        # Third run : building has had the address in the past
        bdg = Building.objects.get(rnb_id="GOOD")
        bdg.addresses_id = []
        bdg.save()

        bdg = find_bdg_to_link(GEOSGeometry(json.dumps(address_point)), "DUMMY")
        self.assertIsNone(bdg)

    def _run_geojson_scenario(self, geojson_data):
        """
        It is possible to "draw" test scenario using geojson.io website
        1. Draw the buildings as polygons (or points), add a type=building property
        2. Draw the plot as a polygon, add a type=plot property
        3. Draw the address point as a point, add a type=address property
        4. Copy/paste the geojson in a new test and run it with this method

        It is possible to visualize the scenario with the geojson.io website
        First copy the geojson in the test
        Paste it in https://jsonlint.com/, then validate and fix it
        Then paste the resulting json in https://geojson.io/ to see the buildings, plots and adress point
        """

        # just to shorten the code
        features = geojson_data["features"]

        # ###
        # 1. We create all the models from the geojson : buildings and plots
        # and retrieve the address point

        address_point = None

        for feature in features:

            # create buildings
            if feature["properties"]["type"] == "building":

                rnb_id = feature["properties"].get("rnb_id", generate_rnb_id())

                Building.objects.create(
                    rnb_id=rnb_id,
                    status="constructed",
                    shape=GEOSGeometry(json.dumps(feature["geometry"])),
                )

            # create plots
            elif feature["properties"]["type"] == "plot":

                # convert the polygon to multipolygon
                multipolygon = {
                    "type": "MultiPolygon",
                    "coordinates": [feature["geometry"]["coordinates"]],
                }

                Plot.objects.create(
                    shape=GEOSGeometry(json.dumps(multipolygon)), id=generate(size=10)
                )

            # retrieve address point
            elif feature["properties"]["type"] == "address":

                address_point = GEOSGeometry(json.dumps(feature["geometry"]))

            else:
                raise Exception("Unknown feature type")

        # ###
        # 2. We search for the building to link to the address point
        return find_bdg_to_link(address_point, "ANY_ADDRESS_ID")
