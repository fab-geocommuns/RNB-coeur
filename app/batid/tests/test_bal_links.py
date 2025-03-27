import json
from django.test import TestCase
from django.contrib.gis.geos import GEOSGeometry
from batid.services.imports.import_bal import bdg_to_link
from batid.models import Building


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

        address_point = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [-0.5198996231682713, 44.83025130621479],
                    "type": "Point",
                }
            )
        )
        bdg = bdg_to_link(address_point, "_")

        self.assertEqual(bdg.rnb_id, "ISOLATED")
