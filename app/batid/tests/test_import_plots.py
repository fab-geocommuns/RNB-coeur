from django.test import TestCase
from unittest.mock import patch
from batid.services import source
import batid.services.imports.import_plots as import_plots
from batid.models import Plot
import os


def fixture_path(filename):
    file_dir = os.path.dirname(os.path.realpath("__file__"))
    return os.path.join(file_dir, "batid/fixtures", filename)


class ImportPlotsTestCase(TestCase):
    @patch("batid.services.imports.import_plots.Source")
    def test_import_plot_data(self, sourceMock):
        # set up the source mock to return a path to our local fixture
        source_instance = sourceMock.return_value
        source_instance.path = fixture_path("cadastre_extract.json")

        # launch the import
        import_plots.import_etalab_plots("75")

        self.assertEqual(Plot.objects.count(), 2)

        plot_1 = Plot.objects.get(id="380010000A0507")
        self.assertEqual(plot_1.shape.geom_type, "MultiPolygon")

        self.assertEqual(
            plot_1.shape,
            "SRID=2154;MULTIPOLYGON (((903244.2888706872 6497030.059134159, 903416.3629750693 6496909.848735239, 903462.0676932482 6496975.65987265, 903461.6522215165 6496975.946153216, 903459.6539579318 6496977.34683543, 903437.060096818 6496993.111918309, 903422.0315617537 6497003.46017521, 903413.8336003702 6497009.122856759, 903363.7203699283 6497044.179738165, 903322.451783876 6497072.917756833, 903307.9325801353 6497082.749749457, 903290.5780950362 6497094.743784005, 903244.2888706872 6497030.059134159)))",
        )

        plot_2 = Plot.objects.get(id="380010000A0507")
        self.assertEqual(
            plot_2.shape,
            "SRID=2154;MULTIPOLYGON (((903244.2888706872 6497030.059134159, 903416.3629750693 6496909.848735239, 903462.0676932482 6496975.65987265, 903461.6522215165 6496975.946153216, 903459.6539579318 6496977.34683543, 903437.060096818 6496993.111918309, 903422.0315617537 6497003.46017521, 903413.8336003702 6497009.122856759, 903363.7203699283 6497044.179738165, 903322.451783876 6497072.917756833, 903307.9325801353 6497082.749749457, 903290.5780950362 6497094.743784005, 903244.2888706872 6497030.059134159)))",
        )
