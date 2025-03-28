import json

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.test import TestCase

from batid.models import Address
from batid.models import Building
from batid.services.imports.import_bal import find_bdg_to_link


class BalLinks(TestCase):
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
        # It should match
        close_address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5205800319222078, 44.83085807431161],
                    "type": "Point",
                }
            )
        )

        bdg = find_bdg_to_link(close_address_point, "_")
        self.assertEqual(bdg.rnb_id, "CLOSE")

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

        # First version of the building have the address
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

        # Second version have the address removed
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
