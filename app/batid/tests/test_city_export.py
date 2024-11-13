import datetime
import json
import os

from django.test import TestCase

from batid.models import Address
from batid.models import Building
from batid.services.building import export_city
from batid.tests.helpers import create_bdg
from batid.tests.helpers import create_grenoble


class TestCityExport(TestCase):
    def setUp(self):
        # Create the city of Grenoble
        create_grenoble()

        # Create two addresses
        address_1 = Address.objects.create(
            id="ban_id_1",
            street_number="1",
            street="rue de la paix",
            city_name="Grenoble",
            city_zipcode="12345",
            city_insee_code="38185",
        )
        address_2 = Address.objects.create(
            id="ban_id_2",
            street_number="2",
            street="rue de la paix",
            city_name="Grenoble",
            city_zipcode="12345",
            city_insee_code="38185",
        )

        # ext ids date : january 1st, 2024
        ext_id_date = datetime.datetime(2024, 1, 1)

        # Create first building
        bdg = create_bdg(
            "XXXXYYYYZZZZ",
            [
                [5.721187072129851, 45.18439363812283],
                [5.721094925229238, 45.184330511384644],
                [5.721122483180295, 45.184274061453465],
                [5.721241326846666, 45.18428316628476],
                [5.721244771590875, 45.184325048490564],
                [5.7212697459849835, 45.18433718825423],
                [5.721187072129851, 45.18439363812283],
            ],
        )

        bdg.addresses_id = [address_1.id]

        # Add some attributes
        bdg.ext_ids = Building.add_ext_id(
            bdg.ext_ids, "bdtopo", "v1", "BAT_BDTOPO_1", ext_id_date.isoformat()
        )
        bdg.ext_ids = Building.add_ext_id(
            bdg.ext_ids, "bdnb", "v8", "BAT_BDNB_1", ext_id_date.isoformat()
        )

        bdg.status = "constructed"
        bdg.save()

        # Create second building
        bdg = create_bdg(
            "AAAABBBBCCCC",
            [
                [5.727718139549069, 45.174683403317374],
                [5.727668380659253, 45.17460155596146],
                [5.727650135732972, 45.17426831908293],
                [5.727782826104686, 45.17423324140296],
                [5.728097965736993, 45.17458752497444],
                [5.727718139549069, 45.174683403317374],
            ],
        )

        bdg.addresses_id = [address_1.id, address_2.id]

        # Add some attributes
        bdg.ext_ids = Building.add_ext_ids(
            bdg.ext_ids, "bdtopo", "v1", "BAT_BDTOPO_2", ext_id_date.isoformat()
        )

        bdg.status = "constructed"
        bdg.save()

    def test_export(self):
        export_path = export_city("38185")

        with open(export_path, "r") as f:
            data = json.load(f)

        expected = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "rnb_id": "AAAABBBBCCCC",
                        "ext_ids": [
                            {
                                "id": "BAT_BDTOPO_2",
                                "source": "bdtopo",
                                "created_at": "2024-01-01T00:00:00",
                                "source_version": "v1",
                            }
                        ],
                        "status": "constructed",
                    },
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [
                                [
                                    [5.727718139549069, 45.174683403317374],
                                    [5.727668380659253, 45.17460155596146],
                                    [5.727650135732972, 45.17426831908293],
                                    [5.727782826104686, 45.17423324140296],
                                    [5.728097965736993, 45.17458752497444],
                                    [5.727718139549069, 45.174683403317374],
                                ]
                            ]
                        ],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {
                        "rnb_id": "XXXXYYYYZZZZ",
                        "ext_ids": [
                            {
                                "id": "BAT_BDTOPO_1",
                                "source": "bdtopo",
                                "created_at": "2024-01-01T00:00:00",
                                "source_version": "v1",
                            },
                            {
                                "id": "BAT_BDNB_1",
                                "source": "bdnb",
                                "created_at": "2024-01-01T00:00:00",
                                "source_version": "v8",
                            },
                        ],
                        "status": "constructed",
                    },
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [
                                [
                                    [5.721187072129851, 45.18439363812283],
                                    [5.721094925229238, 45.184330511384644],
                                    [5.721122483180295, 45.184274061453465],
                                    [5.721241326846666, 45.18428316628476],
                                    [5.721244771590875, 45.184325048490564],
                                    [5.721269745984984, 45.18433718825423],
                                    [5.721187072129851, 45.18439363812283],
                                ]
                            ]
                        ],
                    },
                },
            ],
        }

        self.assertDictEqual(data, expected)

        os.remove(export_path)
