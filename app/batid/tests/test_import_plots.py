from django.test import TestCase
from unittest.mock import patch
from batid.services import source
import batid.services.imports.import_plots as import_plots
from batid.models import Plot
import os
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
import batid.tests.helpers as helpers


class ImportPlotsTestCase(TestCase):
    @patch("batid.services.imports.import_plots.Source")
    def test_import_plot_data(self, sourceMock):
        # set up the source mock to return a path to our local fixture
        source_instance = sourceMock.return_value
        source_instance.path = helpers.fixture_path("cadastre_extract.json")

        # launch the import
        import_plots.import_etalab_plots("75")

        self.assertEqual(Plot.objects.count(), 2)

        plot_1 = Plot.objects.get(id="380010000A0507")
        self.assertEqual(plot_1.shape.geom_type, "MultiPolygon")
        self.assertEqual(plot_1.shape.srid, 2154)
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
