from uuid import UUID

from batid.models import Address
from batid.services.ban_address import resolve_ban_address
from django.test import TestCase

BAN_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_BAN_ID = UUID("22222222-2222-4222-8222-222222222222")
KEY = "75105_8884_00004"


def keys(match) -> set:
    return set(match.addresses.values_list("cle_interop", flat=True))


class ResolveBanAddressTestCase(TestCase):
    def test_ban_id_held_locally(self):
        """
        Input: a local address holds the BAN ID, under another key; another local
        address has the BAN key and no BAN ID.
        Expected: only the address holding the BAN ID, found with "ban_id".
        """
        Address.objects.create(cle_interop="75105_0000_00001", ban_id=BAN_ID)
        Address.objects.create(cle_interop=KEY)

        match = resolve_ban_address(KEY, BAN_ID)

        self.assertEqual(keys(match), {"75105_0000_00001"})
        self.assertEqual(match.found_with, "ban_id")

    def test_ban_id_unknown_falls_back_on_key(self):
        """
        Input: no local address holds the BAN ID; a local address has the key and
        no BAN ID.
        Expected: this address, found with "cle_interop".
        """
        Address.objects.create(cle_interop=KEY)

        match = resolve_ban_address(KEY, BAN_ID)

        self.assertEqual(keys(match), {KEY})
        self.assertEqual(match.found_with, "cle_interop")

    def test_ban_id_unknown_skips_reassigned_key(self):
        """
        Input: no local address holds the BAN ID; the local address with the key
        holds another BAN ID (the key has been reassigned).
        Expected: no address, found with "cle_interop".
        """
        Address.objects.create(cle_interop=KEY, ban_id=OTHER_BAN_ID)

        match = resolve_ban_address(KEY, BAN_ID)

        self.assertEqual(keys(match), set())
        self.assertEqual(match.found_with, "cle_interop")

    def test_ban_id_unknown_ignores_case_and_skips_reassigned_spelling(self):
        """
        Input: no local address holds the BAN ID; the key exists in lowercase with
        no BAN ID and in uppercase with another BAN ID.
        Expected: only the lowercase address, found with "cle_interop".
        """
        Address.objects.create(cle_interop="2a004_abcd_00001")
        Address.objects.create(cle_interop="2A004_ABCD_00001", ban_id=OTHER_BAN_ID)

        match = resolve_ban_address("2A004_abcd_00001", BAN_ID)

        self.assertEqual(keys(match), {"2a004_abcd_00001"})
        self.assertEqual(match.found_with, "cle_interop")

    def test_no_ban_id_matches_key_whatever_local_ban_id(self):
        """
        Input: no BAN ID from the BAN; the key exists in lowercase with no BAN ID
        and in uppercase with a BAN ID.
        Expected: both addresses, found with "cle_interop".
        """
        Address.objects.create(cle_interop="2a004_abcd_00001")
        Address.objects.create(cle_interop="2A004_ABCD_00001", ban_id=OTHER_BAN_ID)

        match = resolve_ban_address("2A004_abcd_00001", None)

        self.assertEqual(keys(match), {"2a004_abcd_00001", "2A004_ABCD_00001"})
        self.assertEqual(match.found_with, "cle_interop")
