from django.test import TestCase
from unittest.mock import patch
from batid.services import source
import batid.services.imports.import_cities as import_cities
from batid.models import City
import os
import json
import batid.tests.helpers as helpers


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
        self.assertEqual(city_1.shape.srid, 2154)

        city_2 = City.objects.get(code_insee="33002")
        # the name has been updated by the duplicate
        self.assertEqual(city_2.name, "Aillas nouveau nom")
        self.assertEqual(city_2.shape.geom_type, "MultiPolygon")
        self.assertEqual(city_2.shape.srid, 2154)
