import json
from unittest.mock import patch

import batid.services.imports.import_cities as import_cities
import batid.tests.helpers as helpers
from batid.models import City
from batid.services.administrative_areas import dpts_list
from batid.services.tchap import TchapLevel
from batid.tasks import queue_full_cities_import
from django.test import SimpleTestCase, TestCase


class ImportCitiesTestCase(TestCase):
    @patch("batid.services.imports.import_cities.fetch_dpt_cities_geojson")
    def test_import_cities_data(self, sourceMock):
        # set up the source mock to return a path to our local fixture
        sourceMock.return_value = json.load(
            open(helpers.fixture_path("cities.geojson"))
        )

        # there are initially no cities
        self.assertEqual(City.objects.count(), 0)

        # launch the import
        import_cities.import_etalab_cities("33")

        # the fixture contains 3 cities, but one is a duplicate
        self.assertEqual(City.objects.count(), 2)

        city_1 = City.objects.get(code_insee="33001")
        self.assertEqual(city_1.name, "Abzac")
        self.assertEqual(city_1.shape.geom_type, "MultiPolygon")
        self.assertEqual(city_1.shape.srid, 4326)

        city_2 = City.objects.get(code_insee="33002")
        # the name has been updated by the duplicate
        self.assertEqual(city_2.name, "Aillas nouveau nom")
        self.assertEqual(city_2.shape.geom_type, "MultiPolygon")
        self.assertEqual(city_2.shape.srid, 4326)


class QueueFullCitiesImport(SimpleTestCase):
    @patch("batid.tasks.notify_tech")
    @patch("batid.tasks.chain")
    def test_end_message_is_the_last_link(self, chain_mock, notify_mock):
        """
        Input: queue_full_cities_import over every department.
        Expected: one import_cities task per department, then the end message task
        "Import des communes terminé" with the department count only (no vintage).
        """
        dpts = dpts_list()

        queue_full_cities_import.run()

        tasks = chain_mock.call_args.args
        self.assertEqual(len(tasks), len(dpts) + 1)
        self.assertEqual([t.args for t in tasks[:-1]], [(dpt,) for dpt in dpts])
        self.assertEqual(tasks[-1].task, "batid.tasks.notify_import_end")
        self.assertTrue(tasks[-1].immutable)
        self.assertEqual(
            tasks[-1].kwargs,
            {
                "title": "Import des communes terminé",
                "details": [["Départements", str(len(dpts))]],
            },
        )
        chain_mock.return_value.assert_called_once_with()
        notify_mock.assert_called_once_with(
            level=TchapLevel.LAUNCH,
            title="Import des communes lancé",
            details=[("Départements", f"{dpts[0]} à {dpts[-1]}")],
        )
