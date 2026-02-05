import uuid
from unittest.mock import patch

from django.test import TestCase

import batid.tests.helpers as helpers
from batid.models import Address
from batid.services.imports.update_addresses_ban import _parse_uuid
from batid.services.imports.update_addresses_ban import _update_batch
from batid.services.imports.update_addresses_ban import flag_addresses_from_ban_file


class TestParseUuid(TestCase):
    def test_valid_uuid(self):
        result = _parse_uuid("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        self.assertEqual(result, uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"))

    def test_empty_string(self):
        result = _parse_uuid("")
        self.assertIsNone(result)

    def test_invalid_uuid(self):
        result = _parse_uuid("not-a-uuid")
        self.assertIsNone(result)


class TestUpdateBatch(TestCase):
    def test_update_existing_address(self):
        Address.objects.create(id="04001_test_00001", source="ban", still_exists=False)

        batch = [
            {
                "cle_interop": "04001_test_00001",
                "ban_id": uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            }
        ]

        updated = _update_batch(batch)

        self.assertEqual(updated, 1)
        addr = Address.objects.get(id="04001_test_00001")
        self.assertTrue(addr.still_exists)
        self.assertEqual(addr.ban_id, uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"))

    def test_address_not_in_db_is_ignored(self):
        batch = [
            {
                "cle_interop": "99999_unknown_00001",
                "ban_id": uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            }
        ]

        updated = _update_batch(batch)

        self.assertEqual(updated, 0)
        self.assertFalse(Address.objects.filter(id="99999_unknown_00001").exists())

    def test_still_exists_false_by_default(self):
        addr = Address.objects.create(
            id="04001_test_00002",
            source="ban",
        )
        self.assertFalse(addr.still_exists)

    def test_update_with_null_ban_id(self):
        Address.objects.create(
            id="04001_test_00003",
            source="ban",
        )

        batch = [
            {
                "cle_interop": "04001_test_00003",
                "ban_id": None,
            }
        ]

        updated = _update_batch(batch)

        self.assertEqual(updated, 1)
        addr = Address.objects.get(id="04001_test_00003")
        self.assertTrue(addr.still_exists)
        self.assertIsNone(addr.ban_id)


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

        # Check first address has ban_id set
        addr1 = Address.objects.get(id="04001_pk624e_00001")
        self.assertTrue(addr1.still_exists)
        self.assertEqual(
            addr1.ban_id, uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        )

        # Check second address has ban_id set
        addr2 = Address.objects.get(id="04001_pk624e_00002")
        self.assertTrue(addr2.still_exists)
        self.assertEqual(
            addr2.ban_id, uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")
        )

        # Check third address has no ban_id (empty in fixture)
        addr3 = Address.objects.get(id="04001_pk624e_00003")
        self.assertTrue(addr3.still_exists)
        self.assertIsNone(addr3.ban_id)

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
    def test_flag_addresses_not_in_ban_stays_false(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create addresses: one in fixture, one not
        Address.objects.create(id="04001_pk624e_00001", source="ban")
        Address.objects.create(id="04001_not_in_ban_00001", source="ban")

        flag_addresses_from_ban_file({"dpt": "04"})

        # Address in fixture should have still_exists=True
        addr_in_ban = Address.objects.get(id="04001_pk624e_00001")
        self.assertTrue(addr_in_ban.still_exists)

        # Address NOT in fixture should still have still_exists=False
        addr_not_in_ban = Address.objects.get(id="04001_not_in_ban_00001")
        self.assertFalse(addr_not_in_ban.still_exists)
