import json
import uuid
from unittest.mock import patch

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.test import TransactionTestCase

import batid.tests.helpers as helpers
from batid.exceptions import BANUnknownCleInterop
from batid.models import Address
from batid.models import Building
from batid.models import BuildingImport
from batid.services.imports.import_bal import create_dpt_bal_rnb_links
from batid.services.imports.import_bal import find_bdg_to_link


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
