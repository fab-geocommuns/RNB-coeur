from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.test import TestCase

from batid.models import Address
from batid.models import Building
from batid.services.imports.import_bal import create_bal_dpt_import_tasks
from batid.services.imports.import_bal import create_bal_full_import_tasks
from batid.services.imports.import_bal import import_addresses
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

    def test_create_bal_full_import_tasks(self):
        dpt_list = ["75", "92"]
        tasks = create_bal_full_import_tasks(dpt_list)

        # Each department creates 4 tasks
        assert len(tasks) == 4

    def test_create_bal_dpt_import_tasks(self):
        tasks = create_bal_dpt_import_tasks("75")

        # The function now creates 2 tasks: dl_source, import_bal
        assert len(tasks) == 2
        assert tasks[0].task == "batid.tasks.dl_source"
        assert tasks[1].task == "batid.tasks.import_bal"

    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bal.Source.remove_uncompressed_folder")
    def test_import_addresses(self, mock_remove_folder, sourceFindMock):

        sourceFindMock.return_value = helpers.fixture_path("bal_simple.csv")
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

        # Verify duplicate addresses were handled correctly (using ignore_conflicts)
        Address.objects.create(
            id="duplicate_address_id",
            source="OTHER",
            point=Point(2.3522, 48.8566, srid=4326),
            street_number="42",
            street_rep="",
            street="Rue Duplicate",
            city_name="Paris",
            city_insee_code="75056",
        )

        # Call the function again
        import_addresses({"dpt": "75"})

        # Verify the original address was not modified
        address_dup = Address.objects.get(id="duplicate_address_id")
        self.assertEqual(address_dup.source, "OTHER")

    # def test_create_link_building_address_no_matches(self):
    #     # Create test data with no matching buildings - using a DataFrame
    #     data = {
    #         "cle_interop": ["test_address_no_match"],
    #         "long": [2],
    #         "lat": [48],
    #         "numero": [123],
    #         "suffixe": [""],
    #         "voie_nom": ["No Match Street"],
    #         "commune_nom": ["Test City"],
    #         "commune_insee": ["12345"],
    #         "certification_commune": [1],
    #     }
    #     df = pd.DataFrame(data)

    #     new_links, _, _ = _create_link_building_address(df)

    #     self.assertEqual(len(new_links), 0)

    # def test_create_link_building_address_with_matches(self):
    #     data = {
    #         "cle_interop": ["test_address_with_match"],
    #         "long": [0.5],
    #         "lat": [0.5],
    #         "numero": [456],
    #         "suffixe": [""],
    #         "voie_nom": ["Match Street"],
    #         "commune_nom": ["Test City"],
    #         "commune_insee": ["12345"],
    #         "certification_commune": [1],
    #     }
    #     df = pd.DataFrame(data)
    #     new_links, _, _ = _create_link_building_address(df)

    #     self.assertGreater(len(new_links), 0)

    #     link = list(new_links)[0]
    #     self.assertEqual(link[0], "TEST123")
    #     self.assertEqual(link[1], "test_address_with_match")

    # def test_create_link_building_address_in_buffer(self):
    #     data = {
    #         "cle_interop": ["test_address_buffer"],
    #         "long": [0.5001],
    #         "lat": [0.5001],
    #         "numero": [789],
    #         "suffixe": [""],
    #         "voie_nom": ["Buffer Street"],
    #         "commune_nom": ["Test City"],
    #         "commune_insee": ["12345"],
    #         "certification_commune": [1],
    #     }
    #     df = pd.DataFrame(data)

    #     new_links, _, _ = _create_link_building_address(df)

    #     self.assertGreater(len(new_links), 0)

    #     link = list(new_links)[0]
    #     self.assertEqual(link[0], "TEST123")
    #     self.assertEqual(link[1], "test_address_buffer")

    # @patch("batid.services.imports.import_bal.Source")
    # @patch("batid.services.imports.import_bal.pd.read_csv")
    # def test_insert_bal_addresses(self, mock_read_csv, MockSource):
    #     mock_source_instance = MagicMock()
    #     source_filepath = "/fake/path/bal_simple.csv"
    #     new_links_filepath = "/fake/path/test_bal_new_links.csv"
    #     mock_source_instance.find.return_value = source_filepath
    #     mock_source_instance.filename = "bal_simple.csv"
    #     MockSource.return_value = mock_source_instance

    #     data = {
    #         "cle_interop": [
    #             "existing_address_id",
    #             "new_address_id1",
    #             "new_address_id2",
    #         ],
    #         "rnb_id": ["TEST123", "TEST123", "TEST123"],
    #         "long": [0.5, 0.6, 0.7],
    #         "lat": [0.5, 0.6, 0.7],
    #         "numero": ["42", "43", "44"],
    #         "suffixe": ["", "bis", ""],
    #         "voie_nom": ["Rue de Test", "Rue de Test", "Avenue Test"],
    #         "commune_nom": ["Paris", "Paris", "Paris"],
    #         "commune_insee": ["75056", "75056", "75056"],
    #         "certification_commune": [1, 1, 1],
    #     }

    #     # Create an existing address
    #     Address.objects.create(
    #         id="existing_address_id",
    #         city_name="Paris",
    #         street="Rue de Test",
    #         street_number="42",
    #     )

    #     mock_read_csv.return_value = pd.DataFrame(data)

    #     insert_bal_addresses({"dpt": "75"})

    #     mock_read_csv.assert_called_once_with(new_links_filepath)

    #     # Check that new addresses were created
    #     self.assertTrue(Address.objects.filter(id="new_address_id1").exists())
    #     self.assertTrue(Address.objects.filter(id="new_address_id2").exists())

    #     # Check address details
    #     new_address1 = Address.objects.get(id="new_address_id1")
    #     self.assertEqual(new_address1.street_number, "43")
    #     self.assertEqual(new_address1.street_rep, "bis")
    #     self.assertEqual(new_address1.street, "Rue de Test")
    #     self.assertEqual(new_address1.city_name, "Paris")
    #     self.assertEqual(new_address1.city_insee_code, "75056")

    #     # Check that the building was updated with the new address IDs
    #     building = Building.objects.get(rnb_id="TEST123")
    #     self.assertIn("existing_address_id", building.addresses_id)
    #     self.assertIn("new_address_id1", building.addresses_id)
    #     self.assertIn("new_address_id2", building.addresses_id)

    # @patch("batid.services.imports.import_bal.Source")
    # @patch("batid.services.imports.import_bal.pd.read_csv")
    # def test_insert_bal_addresses_empty_data(self, mock_read_csv, MockSource):
    #     mock_source_instance = MagicMock()
    #     source_filepath = "/fake/path/bal_simple.csv"
    #     new_links_filepath = "/fake/path/test_bal_new_links.csv"
    #     mock_source_instance.find.return_value = source_filepath
    #     mock_source_instance.filename = "bal_simple.csv"
    #     MockSource.return_value = mock_source_instance

    #     data = {
    #         "cle_interop": [],
    #         "rnb_id": [],
    #         "long": [],
    #         "lat": [],
    #         "numero": [],
    #         "suffixe": [],
    #         "voie_nom": [],
    #         "commune_nom": [],
    #         "commune_insee": [],
    #         "certification_commune": [],
    #     }

    #     mock_read_csv.return_value = pd.DataFrame(data)
    #     initial_address_count = Address.objects.count()

    #     insert_bal_addresses({"dpt": "75"})

    #     mock_read_csv.assert_called_once_with(new_links_filepath)
    #     self.assertEqual(Address.objects.count(), initial_address_count)
