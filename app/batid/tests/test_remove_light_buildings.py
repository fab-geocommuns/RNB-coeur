import os
import tempfile
from unittest.mock import patch

import geopandas as gpd
from batid.services.data_fix.remove_light_buildings import buildings_to_remove
from django.test import SimpleTestCase
from shapely.geometry import Point


class ErrorFile(SimpleTestCase):
    @patch("batid.services.data_fix.remove_light_buildings.connection")
    @patch("batid.services.data_fix.remove_light_buildings.gpd.read_file")
    def test_error_file_keeps_every_failed_building(self, read_file, connection):
        """
        Input: two light BD Topo buildings linked to the RNB ids AAA and BBB, the
        SQL check failing for both.
        Expected: no building to remove, and the error file holds both ids.
        """
        read_file.return_value = gpd.GeoDataFrame(
            {
                "ID": ["1", "2"],
                "IDS_RNB": ["AAA", "BBB"],
                "LEGER": ["Oui", "Oui"],
                "geometry": [Point(700000, 6600000), Point(700100, 6600100)],
            },
            crs="EPSG:2154",
        )
        connection.cursor.return_value.execute.side_effect = Exception("negative")

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                rnb_ids = buildings_to_remove("bdtopo.gpkg")
                with open("log_error_surface.csv") as f:
                    lines = f.read().splitlines()
            finally:
                os.chdir(cwd)

        self.assertEqual(len(rnb_ids), 0)
        self.assertEqual(sorted(lines), ["AAA", "BBB"])
