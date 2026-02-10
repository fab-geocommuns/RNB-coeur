from unittest.mock import patch
from uuid import UUID

from django.test import TestCase

import batid.tests.helpers as helpers
from batid.models import Address
from batid.services.imports.update_addresses_ban import _update_batch
from batid.services.imports.update_addresses_ban import flag_addresses_from_ban_file
from batid.services.imports.update_addresses_ban import normalize_text
from batid.services.imports.update_addresses_ban import (
    update_addresses_text_and_ban_id,
)


class TestUpdateBatch(TestCase):
    def test_update_existing_address(self):
        Address.objects.create(id="04001_test_00001", source="ban")

        batch = [
            {
                "cle_interop": "04001_test_00001",
            }
        ]

        updated = _update_batch(batch)

        self.assertEqual(updated, 1)
        addr = Address.objects.get(id="04001_test_00001")
        self.assertTrue(addr.still_exists)

    def test_address_not_in_db_is_ignored(self):
        batch = [
            {
                "cle_interop": "99999_unknown_00001",
            }
        ]

        updated = _update_batch(batch)

        self.assertEqual(updated, 0)
        self.assertFalse(Address.objects.filter(id="99999_unknown_00001").exists())

    def test_still_exists_none_by_default(self):
        addr = Address.objects.create(
            id="04001_test_00002",
            source="ban",
        )
        self.assertIsNone(addr.still_exists)


class TestFlagAddressesFromBanFile(TestCase):
    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_updates_existing(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create addresses that exist in the fixture
        Address.objects.create(id="04001_pk624e_00001", source="ban")
        Address.objects.create(id="04001_pk624e_00002", source="ban")
        Address.objects.create(id="04001_pk624e_00003", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        self.assertEqual(result["dpt"], "04")
        self.assertEqual(result["updated"], 3)

        # Check addresses have still_exists=True
        addr1 = Address.objects.get(id="04001_pk624e_00001")
        self.assertTrue(addr1.still_exists)

        addr2 = Address.objects.get(id="04001_pk624e_00002")
        self.assertTrue(addr2.still_exists)

        addr3 = Address.objects.get(id="04001_pk624e_00003")
        self.assertTrue(addr3.still_exists)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_ignores_unknown(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create only one address that exists in the fixture
        Address.objects.create(id="04001_pk624e_00001", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        # Only 1 address should be updated (the one that exists in DB)
        self.assertEqual(result["updated"], 1)

        # The unknown address from fixture should not be created
        self.assertFalse(Address.objects.filter(id="04001_unknown_99999").exists())

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_not_in_ban_marked_false(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create addresses: one in fixture, one not
        Address.objects.create(id="04001_pk624e_00001", source="ban")
        Address.objects.create(id="04001_not_in_ban_00001", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        # Address in fixture should have still_exists=True
        addr_in_ban = Address.objects.get(id="04001_pk624e_00001")
        self.assertTrue(addr_in_ban.still_exists)

        # Address NOT in fixture should be marked still_exists=False
        addr_not_in_ban = Address.objects.get(id="04001_not_in_ban_00001")
        self.assertFalse(addr_not_in_ban.still_exists)

        # Check obsolete count in result
        self.assertEqual(result["obsolete"], 1)


class TestNormalizeText(TestCase):
    def test_removes_accents_and_lowercases(self):
        self.assertEqual(normalize_text("Rue de la République"), "rue de la republique")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_text("  hello  "), "hello")

    def test_handles_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_apostrophe(self):
        self.assertEqual(
            normalize_text("Rue de l’Artisanat"), normalize_text("rue de l'artisanat")
        )

    def test_dash(self):
        self.assertEqual(
            normalize_text("chemin du pont vieux"),
            normalize_text("Chemin du Pont-Vieux"),
        )


class TestUpdateAddressesTextAndBanId(TestCase):
    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_matching_text_updates_street_city_and_ban_id(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Fixture row 1: numero=1, rep=bis, nom_voie=Impasse de la Treille,
        # code_postal=04510, code_insee=04001, nom_commune=Aiglun,
        # id_ban_adresse=a1b2c3d4-e5f6-7890-abcd-ef1234567890
        Address.objects.create(
            id="04001_pk624e_00001",
            source="ban",
            still_exists=True,
            street="impasse de la treille",
            street_number="1",
            # test de l'alias B / bis
            street_rep="B",  # alias for "bis" in BAN fixture
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["mismatched"], 0)

        addr = Address.objects.get(id="04001_pk624e_00001")
        self.assertEqual(addr.street, "Impasse de la Treille")
        self.assertEqual(addr.city_name, "Aiglun")
        self.assertEqual(addr.street_rep, "bis")
        self.assertEqual(addr.ban_id, UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"))
        self.assertEqual(addr.ban_update_flag, "update")
        self.assertIsNone(addr.ban_update_details)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_mismatching_text_flags_text_mismatch(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # DB has "rue de la gare" but BAN has "Impasse de la Treille" → mismatch
        Address.objects.create(
            id="04001_pk624e_00002",
            source="ban",
            still_exists=True,
            street="rue de la gare",
            street_number="2",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["mismatched"], 1)

        addr = Address.objects.get(id="04001_pk624e_00002")
        self.assertEqual(addr.ban_update_flag, "text_mismatch")
        # Street should not be updated on mismatch
        self.assertEqual(addr.street, "rue de la gare")
        # Details should contain the mismatched field
        self.assertIn("street", addr.ban_update_details)
        self.assertEqual(addr.ban_update_details["street"]["db"], "rue de la gare")
        self.assertEqual(
            addr.ban_update_details["street"]["ban"], "Impasse de la Treille"
        )

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_no_ban_id_in_file_updates_text_only(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Fixture row 3: id_ban_adresse is empty
        Address.objects.create(
            id="04001_pk624e_00003",
            source="ban",
            still_exists=True,
            street="impasse de la treille",
            street_number="3",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["updated"], 1)

        addr = Address.objects.get(id="04001_pk624e_00003")
        self.assertEqual(addr.street, "Impasse de la Treille")
        self.assertEqual(addr.city_name, "Aiglun")
        self.assertIsNone(addr.ban_id)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_address_not_still_exists_is_skipped(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Address with still_exists=False should be ignored
        Address.objects.create(
            id="04001_pk624e_00001",
            source="ban",
            still_exists=False,
            street="impasse de la treille",
            street_number="1",
            street_rep="bis",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["mismatched"], 0)

        addr = Address.objects.get(id="04001_pk624e_00001")
        # Street should remain unchanged
        self.assertEqual(addr.street, "impasse de la treille")
        self.assertIsNone(addr.ban_id)
