from unittest.mock import patch, MagicMock
import csv
import io

from django.contrib.gis.geos import MultiPolygon, Point
from django.contrib.gis.geos import Polygon
from django.test import TestCase
from django.contrib.gis.db.models.functions import Area
from django.contrib.gis.measure import D

from batid.models import Address
from batid.models import Building
from batid.models import Plot
from batid.services.imports.import_bal import _create_bal_dpt_import_tasks
from batid.services.imports.import_bal import create_bal_full_import_tasks
from batid.services.imports.import_bal import import_addresses
from batid.services.imports.import_bal import _find_link_building_with_address
from batid.services.imports.import_bal import link_building_with_addresses
from batid.tests import helpers


class TestBALImport(TestCase):
    def setUp(self):
        self.test_address = Address.objects.create(
            id="test_address_id",
            city_name="Paris",
            street="Rue de Test",
            street_number="42",
        )

        self.test_building = Building.objects.create(
            rnb_id="TEST123",
            shape=MultiPolygon(Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))),
            is_active=True,
            addresses_id=["test_address_id"],
        )
        
        self.test_plot = Plot.objects.create(
            id="test_plot_id",
            shape=MultiPolygon(Polygon(((0, 0), (0, 1.1), (1.1, 1.1), (1.1, 0), (0, 0)))),
        )

    def test_create_bal_full_import_tasks(self):
        dpt_list = ["75", "92"]
        tasks = create_bal_full_import_tasks(dpt_list)

        # Each department creates 3 tasks (updated from 4)
        assert len(tasks) == 6

    def test_create_bal_dpt_import_tasks(self):
        tasks = _create_bal_dpt_import_tasks("75")

        # The function now creates 3 tasks: dl_source, import_bal, link_building_addresses_using_bal
        assert len(tasks) == 3
        assert tasks[0].task == "batid.tasks.dl_source"
        assert tasks[1].task == "batid.tasks.import_bal"

    @patch("batid.services.imports.import_bal.Source.find")
    @patch("batid.services.imports.import_bal.Source.remove_uncompressed_folder")
    def test_import_addresses(self, mock_remove_folder, mock_source_find):
        mock_source_find.return_value = helpers.fixture_path("bal_simple.csv")
        mock_remove_folder.return_value = None
        initial_address_count = Address.objects.count()

        # Call the function with department parameter
        import_addresses({"dpt": "75"})

        # Verify addresses were created
        self.assertGreater(Address.objects.count(), initial_address_count)

        # Verify specific addresses were created with correct data
        address1 = Address.objects.filter(
            street="Rue de Test", street_number="10"
        ).first()
        self.assertIsNotNone(address1)
        self.assertEqual(address1.source, "BAL")
        self.assertEqual(address1.city_name, "Paris")

        # Verify addresses with certification_commune != "1" were skipped
        uncertified_address = Address.objects.filter(street="Rue Non Certifiée").first()
        self.assertIsNone(uncertified_address)

        # Then update it to have a different source
        Address.objects.filter(id="duplicate_address_id").update(source="OTHER")

        # Call the function again
        import_addresses({"dpt": "75"})

        # Verify the original address was not modified
        address_dup = Address.objects.get(id="duplicate_address_id")
        self.assertEqual(address_dup.source, "OTHER")

    def test_find_link_building_with_address_no_matches(self):
        # Create test data with no matching buildings
        data = [
            {
                "cle_interop": "test_address_no_match",
                "long": "2",
                "lat": "48",
                "numero": "123",
                "suffixe": "",
                "voie_nom": "No Match Street",
                "commune_nom": "Test City",
                "commune_insee": "12345",
                "certification_commune": "1",
            }
        ]

        new_links, _, _ = _find_link_building_with_address(data)

        self.assertEqual(len(new_links), 0)

    def test_find_link_building_with_address_with_matches(self):
        data = [
            {
                "cle_interop": "test_address_with_match",
                "long": "0.5",
                "lat": "0.5",
                "numero": "456",
                "suffixe": "",
                "voie_nom": "Match Street",
                "commune_nom": "Test City",
                "commune_insee": "12345",
                "certification_commune": "1",
            }
        ]
        new_links, _, _ = _find_link_building_with_address(data)

        self.assertEqual(len(new_links), 1)

        link = list(new_links)[0]
        self.assertEqual(link["rnb_id"], "TEST123")
        self.assertEqual(link["cle_interop"], "test_address_with_match")

    def test_find_link_building_with_address_in_buffer(self):
        data = [
            {
                "cle_interop": "test_address_buffer",
                "long": "1.00001",
                "lat": "1.00001",
                "numero": "789",
                "suffixe": "",
                "voie_nom": "Buffer Street",
                "commune_nom": "Test City",
                "commune_insee": "12345",
                "certification_commune": "1",
            }
        ]
        
        # Create an Address object for the test
        Address.objects.create(
            id="test_address_buffer",
            city_name="Test City",
            street="Buffer Street",
            street_number="789",
            point=f'POINT (1.00001 1.00001)',
        )
        
        # Run the function with real database interactions
        new_links, _, _ = _find_link_building_with_address(data)

        self.assertEqual(len(new_links), 1)

        self.assertEqual(new_links[0]["rnb_id"], "TEST123")
        self.assertEqual(new_links[0]["cle_interop"], "test_address_buffer")