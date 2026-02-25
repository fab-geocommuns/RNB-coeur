from unittest.mock import patch

from django.test import TestCase
from django.test import TransactionTestCase

import batid.tests.helpers as helpers
from batid.models import Address
from batid.services.imports.update_addresses_ban import _mark_existing_addresses
from batid.services.imports.update_addresses_ban import (
    delete_unlinked_obsolete_addresses,
)
from batid.services.imports.update_addresses_ban import flag_addresses_from_ban_file


class TestUpdateBatch(TestCase):
    def test_update_existing_address(self):
        Address.objects.create(id="04001_test_00001", source="ban")

        batch = ["04001_test_00001"]

        updated = _mark_existing_addresses(batch)

        self.assertEqual(updated, 1)
        addr = Address.objects.get(id="04001_test_00001")
        self.assertTrue(addr.still_exists)

    def test_address_not_in_db_is_ignored(self):
        batch = ["99999_unknown_00001"]

        updated = _mark_existing_addresses(batch)

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
        self.assertEqual(result["still_exist"], 3)

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
        self.assertEqual(result["still_exist"], 1)

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

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_does_not_touch_other_departments(
        self, mock_remove, mock_find
    ):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create an address in another department
        other_dept_addr = Address.objects.create(id="75001_other_00001", source="ban")

        flag_addresses_from_ban_file({"dpt": "04"})

        # Address from other department should remain untouched (still_exists=None)
        other_dept_addr.refresh_from_db()
        self.assertIsNone(other_dept_addr.still_exists)


class TestDeleteUnlinkedObsoleteAddresses(TransactionTestCase):
    def test_obsolete_address_not_linked_is_deleted(self):
        Address.objects.create(id="04001_old_00001", source="ban", still_exists=False)

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 1})
        self.assertFalse(Address.objects.filter(id="04001_old_00001").exists())

    def test_obsolete_address_linked_to_current_building_is_kept(self):
        Address.objects.create(id="04001_old_00002", source="ban", still_exists=False)
        bdg = helpers.create_default_bdg()
        bdg.addresses_id = ["04001_old_00002"]
        bdg.save()

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 0})
        self.assertTrue(Address.objects.filter(id="04001_old_00002").exists())

    def test_obsolete_address_linked_to_building_history_is_kept(self):
        Address.objects.create(id="04001_old_00003", source="ban", still_exists=False)
        bdg = helpers.create_default_bdg()
        bdg.addresses_id = ["04001_old_00003"]
        bdg.save()

        # Update building with empty addresses — the trigger saves the old
        # version (with the address) to batid_building_history
        bdg.update(
            user=None,
            event_origin={"source": "test"},
            status=None,
            addresses_id=[],
        )

        # Address is no longer in batid_building but still in history
        bdg.refresh_from_db()
        self.assertEqual(bdg.addresses_id, [])

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 0})
        self.assertTrue(Address.objects.filter(id="04001_old_00003").exists())

    def test_address_with_still_exists_true_is_not_touched(self):
        Address.objects.create(id="04001_ok_00001", source="ban", still_exists=True)

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 0})
        self.assertTrue(Address.objects.filter(id="04001_ok_00001").exists())
