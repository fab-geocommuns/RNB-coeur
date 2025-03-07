from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.test import TestCase

import batid.services.imports.import_plots as import_plots
import batid.tests.helpers as helpers
from batid.models import Plot


class ImportPlotsTestCase(TestCase):
    @patch("batid.services.imports.import_plots.Source")
    def test_import_plot_data(self, sourceMock):

        bu_fixture_path = helpers.fixture_path("cadastre_extract_data.json")
        fixture_path = helpers.fixture_path("cadastre_extract_copy.json")

        # We have to make a copy of the origin file since the import process will delete the source file
        with open(bu_fixture_path, "r") as f, open(fixture_path, "w") as f_copy:
            f_copy.write(f.read())

        # set up the source mock to return a path to our local fixture
        source_instance = sourceMock.return_value
        source_instance.path = fixture_path

        # launch the import
        import_plots.import_etalab_plots("75", "2024-12-13", 1)

        self.assertEqual(Plot.objects.count(), 3)

        plot_1 = Plot.objects.get(id="380010000A0507")
        self.assertEqual(plot_1.shape.geom_type, "MultiPolygon")
        self.assertEqual(plot_1.shape.srid, 4326)
        # easiest way I found to test the geometry is coherent is to check there is one close to the middle of the plot
        self.assertEqual(
            Plot.objects.filter(
                shape__distance_lt=(
                    Point(5.606245994567871, 45.54235183402324, srid=4326),
                    D(m=20),
                )
            ).count(),
            1,
        )
        self.assertEqual(plot_1.source_version, "2024-12-13")

        plot_2 = Plot.objects.get(id="380010000A0142")
        self.assertEqual(plot_2.shape.geom_type, "MultiPolygon")
        self.assertEqual(
            Plot.objects.filter(
                shape__distance_lt=(
                    Point(5.614367723464967, 45.544643643344415, srid=4326),
                    D(m=20),
                )
            ).count(),
            1,
        )
        self.assertEqual(plot_2.source_version, "2024-12-13")

        # this one is interesting because its shape is invalid
        # and has to be buffered
        plot_3 = Plot.objects.get(id="010080000A0382")
        self.assertEqual(plot_3.shape.geom_type, "MultiPolygon")
        self.assertEqual(plot_3.source_version, "2024-12-13")
