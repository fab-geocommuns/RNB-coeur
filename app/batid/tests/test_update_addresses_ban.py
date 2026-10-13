import csv
from io import StringIO
from unittest.mock import Mock, patch

import batid.tests.helpers as helpers
from batid.models import Address
from batid.services.imports.update_addresses_ban import (
    _expand_street_abbreviations,
    _is_geocoding_success,
    _mark_existing_addresses,
    _split_housenumber,
    _streets_match,
    compare_addresses_with_ban_file,
    delete_unlinked_obsolete_addresses,
    flag_addresses_from_ban_file,
    geocode_obsolete_addresses,
    normalize_text,
)
from batid.tests.factories.users import UserFactory
from django.contrib.gis.geos import Point
from django.db import connection
from django.test import TestCase, TransactionTestCase


class TestUpdateBatch(TestCase):
    def test_update_existing_address(self):
        Address.objects.create(cle_interop="04001_test_00001", source="ban")

        batch = ["04001_test_00001"]

        updated = _mark_existing_addresses(batch)

        self.assertEqual(updated, 1)
        addr = Address.objects.get(cle_interop="04001_test_00001")
        self.assertTrue(addr.still_exists)

    def test_address_not_in_db_is_ignored(self):
        batch = ["99999_unknown_00001"]

        updated = _mark_existing_addresses(batch)

        self.assertEqual(updated, 0)
        self.assertFalse(
            Address.objects.filter(cle_interop="99999_unknown_00001").exists()
        )

    def test_still_exists_none_by_default(self):
        addr = Address.objects.create(
            cle_interop="04001_test_00002",
            source="ban",
        )
        self.assertIsNone(addr.still_exists)


class TestFlagAddressesFromBanFile(TestCase):
    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_updates_existing(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create addresses that exist in the fixture
        Address.objects.create(cle_interop="04001_pk624e_00001", source="ban")
        Address.objects.create(cle_interop="04001_pk624e_00002", source="ban")
        Address.objects.create(cle_interop="04001_pk624e_00003", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        self.assertEqual(result["dpt"], "04")
        self.assertEqual(result["still_exist"], 3)

        # Check addresses have still_exists=True
        addr1 = Address.objects.get(cle_interop="04001_pk624e_00001")
        self.assertTrue(addr1.still_exists)

        addr2 = Address.objects.get(cle_interop="04001_pk624e_00002")
        self.assertTrue(addr2.still_exists)

        addr3 = Address.objects.get(cle_interop="04001_pk624e_00003")
        self.assertTrue(addr3.still_exists)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_ignores_unknown(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create only one address that exists in the fixture
        Address.objects.create(cle_interop="04001_pk624e_00001", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        # Only 1 address should be updated (the one that exists in DB)
        self.assertEqual(result["still_exist"], 1)

        # The unknown address from fixture should not be created
        self.assertFalse(
            Address.objects.filter(cle_interop="04001_unknown_99999").exists()
        )

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_not_in_ban_marked_false(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create addresses: one in fixture, one not
        Address.objects.create(cle_interop="04001_pk624e_00001", source="ban")
        Address.objects.create(cle_interop="04001_not_in_ban_00001", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        # Address in fixture should have still_exists=True
        addr_in_ban = Address.objects.get(cle_interop="04001_pk624e_00001")
        self.assertTrue(addr_in_ban.still_exists)

        # Address NOT in fixture should be marked still_exists=False
        addr_not_in_ban = Address.objects.get(cle_interop="04001_not_in_ban_00001")
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
        other_dept_addr = Address.objects.create(
            cle_interop="75001_other_00001", source="ban"
        )

        flag_addresses_from_ban_file({"dpt": "04"})

        # Address from other department should remain untouched (still_exists=None)
        other_dept_addr.refresh_from_db()
        self.assertIsNone(other_dept_addr.still_exists)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_corsica_keys_any_case(self, mock_remove, mock_find):
        """
        Input: Corsica department "2A" (uppercase), two addresses absent from the
        BAN file, one with a lowercase key "2a004_..." and one with an uppercase
        key "2A004_...".
        Expected: both addresses are marked still_exists=False, 2 obsolete reported.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        Address.objects.create(cle_interop="2a004_0010_00001", source="ban")
        Address.objects.create(cle_interop="2A004_0010_00002", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "2A"})

        self.assertEqual(result["obsolete"], 2)
        for cle_interop in ["2a004_0010_00001", "2A004_0010_00002"]:
            addr = Address.objects.get(cle_interop=cle_interop)
            self.assertFalse(addr.still_exists)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_keys_compared_case_insensitively(
        self, mock_remove, mock_find
    ):
        """
        Input: an address with an uppercase key "04001_PK624E_00001" whose
        lowercase version is in the BAN file.
        Expected: the address is marked still_exists=True, 1 still existing and
        0 obsolete reported.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        Address.objects.create(cle_interop="04001_PK624E_00001", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "04"})

        self.assertEqual(result["still_exist"], 1)
        self.assertEqual(result["obsolete"], 0)
        addr = Address.objects.get(cle_interop="04001_PK624E_00001")
        self.assertTrue(addr.still_exists)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_flag_addresses_uppercase_file_keys_match_lowercase_db_keys(
        self, mock_remove, mock_find
    ):
        """
        Input: a BAN file holding uppercase keys ("2A004_0010_00001",
        "2A004_0010_00002") and two addresses in db with lowercase keys:
        "2a004_0010_00001" (in the file in uppercase) and "2a004_0010_00003"
        (absent from the file).
        Expected: "2a004_0010_00001" is marked still_exists=True and is not
        marked obsolete, "2a004_0010_00003" is marked still_exists=False;
        1 still existing and 1 obsolete reported.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_uppercase_keys.csv")

        Address.objects.create(cle_interop="2a004_0010_00001", source="ban")
        Address.objects.create(cle_interop="2a004_0010_00003", source="ban")

        result = flag_addresses_from_ban_file({"dpt": "2A"})

        self.assertEqual(result["still_exist"], 1)
        self.assertEqual(result["obsolete"], 1)
        self.assertTrue(
            Address.objects.get(cle_interop="2a004_0010_00001").still_exists
        )
        self.assertFalse(
            Address.objects.get(cle_interop="2a004_0010_00003").still_exists
        )


class TestNormalizeText(TestCase):
    def test_removes_accents_and_lowercases(self):
        self.assertEqual(normalize_text("Rue de la République"), "rue de la republique")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_text("  hello  "), "hello")

    def test_handles_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_apostrophe(self):
        self.assertEqual(
            normalize_text("Rue de l'Artisanat"), normalize_text("rue de l'artisanat")
        )

    def test_dash(self):
        self.assertEqual(
            normalize_text("chemin du pont vieux"),
            normalize_text("Chemin du Pont-Vieux"),
        )


class TestExpandStreetAbbreviations(TestCase):
    def test_expands_first_word(self):
        self.assertEqual(
            _expand_street_abbreviations("imp des lilas"), "impasse des lilas"
        )

    def test_expands_chemin(self):
        self.assertEqual(
            _expand_street_abbreviations("che du moulin"), "chemin du moulin"
        )

    def test_no_expansion_when_no_abbreviation(self):
        self.assertEqual(_expand_street_abbreviations("rue des lilas"), "rue des lilas")

    def test_empty_string(self):
        self.assertEqual(_expand_street_abbreviations(""), "")

    def test_only_first_word_is_expanded(self):
        self.assertEqual(
            _expand_street_abbreviations("av imp des lilas"), "avenue imp des lilas"
        )


class TestStreetsMatch(TestCase):
    def test_exact_match(self):
        self.assertTrue(_streets_match("Rue des Lilas", "Rue des Lilas"))

    def test_match_with_case_and_accents(self):
        self.assertTrue(_streets_match("rue de la république", "Rue de la République"))

    def test_du_vs_des(self):
        # Levenshtein distance of 2 between "du" and "des"
        self.assertTrue(_streets_match("Rue du Moulin", "Rue des Moulin"))

    def test_abbreviation_imp(self):
        self.assertTrue(_streets_match("Imp de la Treille", "Impasse de la Treille"))

    def test_abbreviation_che(self):
        self.assertTrue(_streets_match("Che du Pont Vieux", "Chemin du Pont Vieux"))

    def test_abbreviation_plus_small_diff(self):
        # "Imp du Moulin" → expand → "impasse du moulin"
        # "Impasse des Moulin" → "impasse des moulin"
        # Levenshtein("impasse du moulin", "impasse des moulin") = 2 → match
        self.assertTrue(_streets_match("Imp du Moulin", "Impasse des Moulin"))

    def test_large_difference_no_match(self):
        self.assertFalse(_streets_match("Rue de la Gare", "Impasse de la Treille"))

    def test_none_db_street(self):
        self.assertFalse(_streets_match(None, "Rue des Lilas"))

    def test_both_empty(self):
        self.assertTrue(_streets_match("", ""))

    def test_single_char_difference(self):
        # Levenshtein distance = 1
        self.assertTrue(_streets_match("Rue des Lilas", "Rue des Lilac"))


@patch("batid.services.imports.update_addresses_ban.Source.find")
@patch("batid.services.imports.update_addresses_ban.os.remove")
class TestCompareAddressesWithBanFile(TestCase):
    # Fixture rows (ban_with_ids_test_data.csv), all in "Impasse de la Treille
    # 04510 Aiglun" (04001):
    # - 04001_pk624e_00001: 1 bis, lon=6.135212, lat=44.070028, with a ban_id
    # - 04001_pk624e_00002: 2, lon=6.135332, lat=44.069986, with a ban_id
    # - 04001_pk624e_00003: 3, no ban_id

    @staticmethod
    def _existing_address(cle_interop: str, **fields):
        values = {
            "street": "impasse de la treille",
            "city_name": "aiglun",
            "city_zipcode": "04510",
            "city_insee_code": "04001",
        }
        values.update(fields)
        return Address.objects.create(
            cle_interop=cle_interop, source="ban", still_exists=True, **values
        )

    def test_matching_fields_are_a_success_with_full_details(
        self, mock_remove, mock_find
    ):
        """
        Input: 3 existing addresses whose fields match the BAN file once
        normalized: lowercase text and "B" for "bis" (row 1, ~5 m away), "Imp"
        for "Impasse" (row 2) and a 2-letter typo (row 3).
        Expected: 3 "comparison_success". The details of row 1 hold the BAN
        address field by field, the distance and no diffs. The addresses
        themselves are untouched.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address(
            "04001_pk624e_00001",
            street_number="1",
            street_rep="B",
            point=Point(6.13518, 44.07000, srid=4326),
        )
        self._existing_address(
            "04001_pk624e_00002", street_number="2", street="Imp de la Treille"
        )
        self._existing_address(
            "04001_pk624e_00003", street_number="3", street="Impasse de las Treilles"
        )

        result = compare_addresses_with_ban_file({"dpt": "04"})

        self.assertEqual(result, {"dpt": "04", "successes": 3, "failures": 0})
        self.assertEqual(
            Address.objects.filter(ban_update_flag="comparison_success").count(), 3
        )

        addr = Address.objects.get(cle_interop="04001_pk624e_00001")
        details = addr.ban_update_details
        self.assertLess(details.pop("distance_m"), 20)
        self.assertEqual(
            details,
            {
                "cle_interop": "04001_pk624e_00001",
                "ban_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "street_number": "1",
                "street_rep": "bis",
                "street": "Impasse de la Treille",
                "city_zipcode": "04510",
                "city_name": "Aiglun",
                "city_insee_code": "04001",
                "lon": 6.135212,
                "lat": 44.070028,
                "diffs": {},
            },
        )
        self.assertEqual(addr.street, "impasse de la treille")
        self.assertEqual(addr.street_rep, "B")
        self.assertIsNone(addr.ban_id)

    def test_mismatching_fields_without_point_are_a_failure(
        self, mock_remove, mock_find
    ):
        """
        Input: an existing address without point, "rue de la gare" in db and
        "Impasse de la Treille" in the BAN file.
        Expected: "comparison_failure", the details hold the BAN address, a null
        distance and the street diff. The street is untouched.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address(
            "04001_pk624e_00002", street_number="2", street="rue de la gare"
        )

        result = compare_addresses_with_ban_file({"dpt": "04"})

        self.assertEqual(result["failures"], 1)
        addr = Address.objects.get(cle_interop="04001_pk624e_00002")
        self.assertEqual(addr.ban_update_flag, "comparison_failure")
        self.assertEqual(addr.ban_update_details["street"], "Impasse de la Treille")
        self.assertIsNone(addr.ban_update_details["distance_m"])
        self.assertEqual(
            addr.ban_update_details["diffs"],
            {"street": {"db": "rue de la gare", "ban": "Impasse de la Treille"}},
        )
        self.assertEqual(addr.street, "rue de la gare")

    def test_no_ban_id_in_file(self, mock_remove, mock_find):
        """
        Input: an existing address matching row 3, which has no ban_id.
        Expected: "comparison_success" with a null ban_id in the details.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address("04001_pk624e_00003", street_number="3")

        compare_addresses_with_ban_file({"dpt": "04"})

        addr = Address.objects.get(cle_interop="04001_pk624e_00003")
        self.assertEqual(addr.ban_update_flag, "comparison_success")
        self.assertIsNone(addr.ban_update_details["ban_id"])

    def test_obsolete_and_already_flagged_addresses_are_skipped(
        self, mock_remove, mock_find
    ):
        """
        Input: an obsolete address (still_exists=False) and an existing address
        already flagged (a previous run), both in the BAN file.
        Expected: nothing compared, both keep their flag.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        obsolete = self._existing_address("04001_pk624e_00001", street_number="1")
        Address.objects.filter(internal_id=obsolete.internal_id).update(
            still_exists=False
        )
        self._existing_address(
            "04001_pk624e_00002",
            street_number="2",
            ban_update_flag="comparison_failure",
        )

        result = compare_addresses_with_ban_file({"dpt": "04"})

        self.assertEqual(result, {"dpt": "04", "successes": 0, "failures": 0})
        obsolete.refresh_from_db()
        self.assertIsNone(obsolete.ban_update_flag)
        self.assertEqual(
            Address.objects.get(cle_interop="04001_pk624e_00002").ban_update_flag,
            "comparison_failure",
        )

    def test_close_distance_is_a_success_despite_field_diffs(
        self, mock_remove, mock_find
    ):
        """
        Input: an existing address ~5 m away from its BAN position, with another
        street name.
        Expected: "comparison_success", the street diff is still in the details.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address(
            "04001_pk624e_00002",
            street_number="2",
            street="rue de la gare",
            point=Point(6.13530, 44.06996, srid=4326),
        )

        compare_addresses_with_ban_file({"dpt": "04"})

        addr = Address.objects.get(cle_interop="04001_pk624e_00002")
        self.assertEqual(addr.ban_update_flag, "comparison_success")
        self.assertLess(addr.ban_update_details["distance_m"], 20)
        self.assertIn("street", addr.ban_update_details["diffs"])

    def test_far_distance_with_matching_fields_is_a_success(
        self, mock_remove, mock_find
    ):
        """
        Input: an existing address ~500 m away from its BAN position, with
        matching fields.
        Expected: "comparison_success" with the distance in the details.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address(
            "04001_pk624e_00001",
            street_number="1",
            street_rep="B",
            point=Point(6.14, 44.073, srid=4326),
        )

        compare_addresses_with_ban_file({"dpt": "04"})

        addr = Address.objects.get(cle_interop="04001_pk624e_00001")
        self.assertEqual(addr.ban_update_flag, "comparison_success")
        self.assertGreater(addr.ban_update_details["distance_m"], 20)

    def test_far_distance_with_field_diffs_is_a_failure(self, mock_remove, mock_find):
        """
        Input: an existing address ~500 m away from its BAN position, with
        another street name.
        Expected: "comparison_failure" with the distance and the street diff in
        the details.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address(
            "04001_pk624e_00002",
            street_number="2",
            street="rue de la gare",
            point=Point(6.14, 44.073, srid=4326),
        )

        compare_addresses_with_ban_file({"dpt": "04"})

        addr = Address.objects.get(cle_interop="04001_pk624e_00002")
        self.assertEqual(addr.ban_update_flag, "comparison_failure")
        self.assertGreater(addr.ban_update_details["distance_m"], 20)
        self.assertIn("street", addr.ban_update_details["diffs"])

    def test_uppercase_key_is_compared_with_the_file_key(
        self, mock_remove, mock_find
    ):
        """
        Input: an existing address with an uppercase key "04001_PK624E_00002",
        whose lowercase version is in the BAN file.
        Expected: "comparison_success", details["cle_interop"] is the key of the
        BAN file (lowercase).
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address("04001_PK624E_00002", street_number="2")

        compare_addresses_with_ban_file({"dpt": "04"})

        addr = Address.objects.get(cle_interop="04001_PK624E_00002")
        self.assertEqual(addr.ban_update_flag, "comparison_success")
        self.assertEqual(addr.ban_update_details["cle_interop"], "04001_pk624e_00002")

    def test_null_string_rep_matches_an_empty_rep(self, mock_remove, mock_find):
        """
        Input: an existing address ~500 m away from its BAN position, holding
        the string "null" as street_rep, while the BAN file has no suffix.
        Expected: "comparison_success" without diffs.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        self._existing_address(
            "04001_pk624e_00002",
            street_number="2",
            street_rep="null",
            point=Point(6.14, 44.073, srid=4326),
        )

        compare_addresses_with_ban_file({"dpt": "04"})

        addr = Address.objects.get(cle_interop="04001_pk624e_00002")
        self.assertEqual(addr.ban_update_flag, "comparison_success")
        self.assertEqual(addr.ban_update_details["diffs"], {})

    def test_duplicate_ban_id_in_file(self, mock_remove, mock_find):
        """
        Input: two existing addresses whose BAN file rows share the same
        id_ban_adresse (it happens in real BAN files).
        Expected: both are compared and their details hold this ban_id: the
        later update has to deal with the duplicate.
        """
        mock_find.return_value = helpers.fixture_path(
            "ban_with_ids_duplicate_ban_id.csv"
        )
        for cle_interop, city_name, city_insee_code in [
            ("85288_p1h9zg_02965", "talmont-saint-hilaire", "85288"),
            ("85103_0099_02965", "grosbreuil", "85103"),
        ]:
            self._existing_address(
                cle_interop,
                street="route de la martiniere",
                street_number="2965",
                city_name=city_name,
                city_zipcode="85440",
                city_insee_code=city_insee_code,
            )

        result = compare_addresses_with_ban_file({"dpt": "85"})

        self.assertEqual(result, {"dpt": "85", "successes": 2, "failures": 0})
        self.assertEqual(
            {addr.ban_update_details["ban_id"] for addr in Address.objects.all()},
            {"9e63d301-1c76-4d33-a508-9ea9e39293d2"},
        )


class TestDeleteUnlinkedObsoleteAddresses(TransactionTestCase):
    @staticmethod
    def _link_addresses(bdg, addresses_cle_interop):
        # bdg.save() is Django's native save (tests only): it bypasses the
        # business functions, so addresses_internal_id is resolved here.
        bdg.addresses_internal_id = Address.internal_ids_from_cle_interop(
            addresses_cle_interop
        )
        bdg.save()

    @staticmethod
    def _protection_trigger_enabled_state():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgenabled FROM pg_trigger "
                "WHERE tgname = 'prevent_delete_linked_address_trigger'"
            )
            return cursor.fetchone()[0]

    def test_obsolete_address_not_linked_is_deleted(self):
        """
        Input: an obsolete address (still_exists=False) referenced by no building.
        Expected: the address is deleted, 1 deletion reported.
        """
        Address.objects.create(
            cle_interop="04001_old_00001", source="ban", still_exists=False
        )

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 1})
        self.assertFalse(Address.objects.filter(cle_interop="04001_old_00001").exists())

    def test_obsolete_address_linked_to_current_building_is_kept(self):
        """
        Input: an obsolete address referenced by a current building.
        Expected: the address is kept, 0 deletion reported.
        """
        Address.objects.create(
            cle_interop="04001_old_00002", source="ban", still_exists=False
        )
        bdg = helpers.create_default_bdg()
        self._link_addresses(bdg, ["04001_old_00002"])

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 0})
        self.assertTrue(Address.objects.filter(cle_interop="04001_old_00002").exists())

    def test_obsolete_address_linked_to_building_history_is_kept(self):
        """
        Input: an obsolete address referenced only by a past version of a
        building (the building was then updated to drop it).
        Expected: the address is kept, 0 deletion reported.
        """
        Address.objects.create(
            cle_interop="04001_old_00003", source="ban", still_exists=False
        )
        bdg = helpers.create_default_bdg()
        self._link_addresses(bdg, ["04001_old_00003"])

        # Update building with empty addresses — the trigger saves the old
        # version (with the address) to batid_building_history
        bdg.update(
            user=UserFactory(username="test_user"),
            event_origin={"source": "test"},
            status=None,
            addresses_cle_interop=[],
        )

        # Address is no longer in batid_building but still in history
        bdg.refresh_from_db()
        self.assertEqual(bdg.addresses_internal_id, [])

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 0})
        self.assertTrue(Address.objects.filter(cle_interop="04001_old_00003").exists())

    def test_address_with_still_exists_true_is_not_touched(self):
        """
        Input: an address still existing in the BAN (still_exists=True),
        referenced by no building.
        Expected: the address is kept, 0 deletion reported.
        """
        Address.objects.create(
            cle_interop="04001_ok_00001", source="ban", still_exists=True
        )

        deleted = delete_unlinked_obsolete_addresses()

        self.assertEqual(deleted, {"deleted_addresses": 0})
        self.assertTrue(Address.objects.filter(cle_interop="04001_ok_00001").exists())

    def test_mixed_addresses_over_several_batches(self):
        """
        Input: 3 unlinked obsolete addresses, 1 obsolete address linked to a
        building, 1 unlinked still existing address, batch_size=1.
        Expected: only the 3 unlinked obsolete addresses are deleted (over
        several batches), 3 deletions reported.
        """
        for i in range(1, 4):
            Address.objects.create(
                cle_interop=f"04001_old_1000{i}", source="ban", still_exists=False
            )
        Address.objects.create(
            cle_interop="04001_old_10004", source="ban", still_exists=False
        )
        Address.objects.create(
            cle_interop="04001_ok_10005", source="ban", still_exists=True
        )
        bdg = helpers.create_default_bdg()
        self._link_addresses(bdg, ["04001_old_10004"])

        deleted = delete_unlinked_obsolete_addresses(batch_size=1)

        self.assertEqual(deleted, {"deleted_addresses": 3})
        self.assertEqual(
            set(Address.objects.values_list("cle_interop", flat=True)),
            {"04001_old_10004", "04001_ok_10005"},
        )

    def test_batch_of_linked_addresses_does_not_stop_the_run(self):
        """
        Input: 2 obsolete addresses linked to a building, created first (lowest
        internal_id), then 1 unlinked obsolete address, batch_size=2.
        Expected: the first batch deletes nothing, the run goes on and deletes
        the unlinked address in the second batch, 1 deletion reported.
        """
        for i in range(1, 4):
            Address.objects.create(
                cle_interop=f"04001_old_2000{i}", source="ban", still_exists=False
            )
        bdg = helpers.create_default_bdg()
        self._link_addresses(bdg, ["04001_old_20001", "04001_old_20002"])

        deleted = delete_unlinked_obsolete_addresses(batch_size=2)

        self.assertEqual(deleted, {"deleted_addresses": 1})
        self.assertEqual(
            set(Address.objects.values_list("cle_interop", flat=True)),
            {"04001_old_20001", "04001_old_20002"},
        )

    def test_protection_trigger_is_enabled_after_run(self):
        """
        Input: one unlinked obsolete address, then a run of the function.
        Expected: the prevent_delete_linked_address_trigger is enabled again
        after the run (tgenabled = 'O').
        """
        Address.objects.create(
            cle_interop="04001_old_00004", source="ban", still_exists=False
        )

        delete_unlinked_obsolete_addresses()

        self.assertEqual(self._protection_trigger_enabled_state(), "O")

    def test_protection_trigger_is_enabled_after_failure(self):
        """
        Input: a run of the function interrupted by an error raised after the
        first deletion batch.
        Expected: the error is propagated and the
        prevent_delete_linked_address_trigger is enabled again (tgenabled = 'O').
        """
        Address.objects.create(
            cle_interop="04001_old_00005", source="ban", still_exists=False
        )

        with patch(
            "batid.services.imports.update_addresses_ban.logger.info",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                delete_unlinked_obsolete_addresses()

        self.assertEqual(self._protection_trigger_enabled_state(), "O")


# Point of "1 Place de la Mairie 04510 Aiglun" in the geocoder results below
GEOCODED_LON = 6.143959
GEOCODED_LAT = 44.050963


def _geocoder_result(**overrides) -> dict:
    """Result columns of the BAN batch geocoder for "1 Place de la Mairie 04510
    Aiglun", a housenumber with a high score."""
    result = {
        "result_id": "04001_0040_00001",
        "result_banId": "2fbce2cc-1ad7-422a-ac99-722dd94760d3",
        "result_type": "housenumber",
        "result_score": "0.9",
        "result_label": "1 Place de la Mairie 04510 Aiglun",
        "result_housenumber": "1",
        "result_street": "Place de la Mairie",
        "result_postcode": "04510",
        "result_city": "Aiglun",
        "result_citycode": "04001",
        "longitude": str(GEOCODED_LON),
        "latitude": str(GEOCODED_LAT),
    }
    result.update(overrides)
    return result


@patch("batid.services.imports.update_addresses_ban.BanBatchGeocoder.geocode")
class TestGeocodeObsoleteAddresses(TestCase):
    @staticmethod
    def _answer(mock_geocode, results_by_street: dict):
        """Make the mocked geocoder answer a CSV like the real one: the sent
        columns followed by the result columns, taken from results_by_street
        (keyed by the sent "voie"), empty when the street is not in it."""

        def geocode(data, columns, citycode_col, result_columns):
            out = StringIO()
            writer = csv.DictWriter(
                out, fieldnames=list(data[0].keys()) + result_columns
            )
            writer.writeheader()
            for row in data:
                writer.writerow({**row, **results_by_street.get(row["voie"], {})})
            return Mock(status_code=200, text=out.getvalue())

        mock_geocode.side_effect = geocode

    @staticmethod
    def _obsolete_address(cle_interop: str, street: str, **fields):
        values = {
            "street_number": "1",
            "street": street,
            "city_zipcode": "04510",
            "city_name": "Aiglun",
            "city_insee_code": "04001",
            "point": Point(GEOCODED_LON, GEOCODED_LAT, srid=4326),
        }
        values.update(fields)
        return Address.objects.create(
            cle_interop=cle_interop, source="ban", still_exists=False, **values
        )

    def test_success_stores_full_details(self, mock_geocode):
        """
        Input: an obsolete address geocoded as a housenumber with a 0.9 score,
        at the same position.
        Expected: flag "geocoding_success", details hold the geocoded address
        field by field, the score, the type and a 0 m distance. The address
        fields themselves are untouched.
        """
        addr = self._obsolete_address("04001_old_00001", "place de la mairie")
        self._answer(mock_geocode, {"place de la mairie": _geocoder_result()})

        result = geocode_obsolete_addresses()

        self.assertEqual(result, {"geocoding_successes": 1, "geocoding_failures": 0})
        addr.refresh_from_db()
        self.assertEqual(addr.ban_update_flag, "geocoding_success")
        self.assertEqual(
            addr.ban_update_details,
            {
                "cle_interop": "04001_0040_00001",
                "ban_id": "2fbce2cc-1ad7-422a-ac99-722dd94760d3",
                "street_number": "1",
                "street_rep": None,
                "street": "Place de la Mairie",
                "city_zipcode": "04510",
                "city_name": "Aiglun",
                "city_insee_code": "04001",
                "lon": GEOCODED_LON,
                "lat": GEOCODED_LAT,
                "label": "1 Place de la Mairie 04510 Aiglun",
                "type": "housenumber",
                "score": 0.9,
                "distance_m": 0.0,
            },
        )
        self.assertEqual(addr.cle_interop, "04001_old_00001")
        self.assertEqual(addr.street, "place de la mairie")
        self.assertFalse(addr.still_exists)

    def test_low_score_but_close_is_a_success(self, mock_geocode):
        """
        Input: an obsolete address geocoded as a housenumber with a 0.6 score,
        about 11 m away.
        Expected: flag "geocoding_success".
        """
        addr = self._obsolete_address(
            "04001_old_00002",
            "place de la mairie",
            point=Point(GEOCODED_LON, GEOCODED_LAT + 0.0001, srid=4326),
        )
        self._answer(
            mock_geocode,
            {"place de la mairie": _geocoder_result(result_score="0.6")},
        )

        geocode_obsolete_addresses()

        addr.refresh_from_db()
        self.assertEqual(addr.ban_update_flag, "geocoding_success")
        self.assertLess(addr.ban_update_details["distance_m"], 20)

    def test_low_score_and_far_is_a_failure_with_details(self, mock_geocode):
        """
        Input: an obsolete address geocoded as a housenumber with a 0.6 score,
        about 500 m away.
        Expected: flag "geocoding_failure", details still hold the proposed
        address, its score and the distance.
        """
        addr = self._obsolete_address(
            "04001_old_00003",
            "place de la mairie",
            point=Point(GEOCODED_LON + 0.006, GEOCODED_LAT, srid=4326),
        )
        self._answer(
            mock_geocode,
            {"place de la mairie": _geocoder_result(result_score="0.6")},
        )

        result = geocode_obsolete_addresses()

        self.assertEqual(result, {"geocoding_successes": 0, "geocoding_failures": 1})
        addr.refresh_from_db()
        self.assertEqual(addr.ban_update_flag, "geocoding_failure")
        self.assertEqual(addr.ban_update_details["cle_interop"], "04001_0040_00001")
        self.assertEqual(addr.ban_update_details["score"], 0.6)
        self.assertGreater(addr.ban_update_details["distance_m"], 400)

    def test_lost_suffix_is_a_failure(self, mock_geocode):
        """
        Input: an obsolete address "1 bis place de la mairie" geocoded as "1
        Place de la Mairie" (no suffix) with a 0.9 score, about 100 m away.
        Expected: flag "geocoding_failure", although score and distance alone
        would make it a success.
        """
        addr = self._obsolete_address(
            "04001_old_00001_bis",
            "place de la mairie",
            street_rep="bis",
            point=Point(GEOCODED_LON, GEOCODED_LAT + 0.0009, srid=4326),
        )
        self._answer(mock_geocode, {"place de la mairie": _geocoder_result()})

        geocode_obsolete_addresses()

        addr.refresh_from_db()
        self.assertEqual(addr.ban_update_flag, "geocoding_failure")
        self.assertIsNone(addr.ban_update_details["street_rep"])

    def test_street_result_is_a_failure(self, mock_geocode):
        """
        Input: an obsolete address geocoded as a street (no housenumber) with a
        0.95 score.
        Expected: flag "geocoding_failure".
        """
        addr = self._obsolete_address("04001_old_00004", "place de la mairie")
        self._answer(
            mock_geocode,
            {
                "place de la mairie": _geocoder_result(
                    result_type="street",
                    result_id="04001_0040",
                    result_score="0.95",
                    result_housenumber="",
                )
            },
        )

        geocode_obsolete_addresses()

        addr.refresh_from_db()
        self.assertEqual(addr.ban_update_flag, "geocoding_failure")
        self.assertEqual(addr.ban_update_details["type"], "street")

    def test_no_result_is_a_failure(self, mock_geocode):
        """
        Input: an obsolete address the geocoder finds nothing for (empty result
        columns).
        Expected: flag "geocoding_failure", every details value is None.
        """
        addr = self._obsolete_address("04001_old_00005", "chemin inconnu")
        self._answer(mock_geocode, {})

        geocode_obsolete_addresses()

        addr.refresh_from_db()
        self.assertEqual(addr.ban_update_flag, "geocoding_failure")
        self.assertTrue(
            all(value is None for value in addr.ban_update_details.values())
        )

    def test_only_unprocessed_obsolete_addresses_are_geocoded(self, mock_geocode):
        """
        Input: an obsolete address not yet geocoded, an obsolete address already
        geocoded (ban_update_flag set), an existing address (still_exists=True)
        and an unchecked one (still_exists=None).
        Expected: only the first one is sent to the geocoder, the others keep
        their flag.
        """
        to_geocode = self._obsolete_address("04001_old_00006", "place de la mairie")
        already_geocoded = self._obsolete_address(
            "04001_old_00007", "rue deja faite", ban_update_flag="geocoding_failure"
        )
        existing = Address.objects.create(
            cle_interop="04001_ok_00001", source="ban", still_exists=True
        )
        unchecked = Address.objects.create(cle_interop="04001_new_00001", source="ban")
        self._answer(mock_geocode, {"place de la mairie": _geocoder_result()})

        geocode_obsolete_addresses()

        mock_geocode.assert_called_once()
        sent = mock_geocode.call_args.kwargs["data"]
        self.assertEqual([row["internal_id"] for row in sent], [to_geocode.internal_id])
        already_geocoded.refresh_from_db()
        self.assertEqual(already_geocoded.ban_update_flag, "geocoding_failure")
        existing.refresh_from_db()
        self.assertIsNone(existing.ban_update_flag)
        unchecked.refresh_from_db()
        self.assertIsNone(unchecked.ban_update_flag)

    def test_suffix_is_sent_apart_from_the_number(self, mock_geocode):
        """
        Input: an obsolete address "11 bis avenue de segur".
        Expected: the geocoder gets the number and the suffix in two columns,
        both used to build the query, and the city code as a filter.
        """
        self._obsolete_address(
            "75107_old_00011_b", "avenue de segur", street_number="11", street_rep="bis"
        )
        self._answer(mock_geocode, {})

        geocode_obsolete_addresses()

        kwargs = mock_geocode.call_args.kwargs
        self.assertEqual(
            kwargs["columns"], ["numero", "rep", "voie", "postcode", "city"]
        )
        self.assertEqual(kwargs["citycode_col"], "citycode")
        sent = kwargs["data"][0]
        self.assertEqual((sent["numero"], sent["rep"]), ("11", "bis"))

    def test_several_batches(self, mock_geocode):
        """
        Input: 3 obsolete addresses, batch_size=2.
        Expected: 2 calls to the geocoder, the 3 addresses are flagged, 3
        successes reported.
        """
        for i in range(1, 4):
            self._obsolete_address(f"04001_old_1000{i}", "place de la mairie")
        self._answer(mock_geocode, {"place de la mairie": _geocoder_result()})

        result = geocode_obsolete_addresses(batch_size=2)

        self.assertEqual(mock_geocode.call_count, 2)
        self.assertEqual(result, {"geocoding_successes": 3, "geocoding_failures": 0})
        self.assertEqual(
            Address.objects.filter(ban_update_flag="geocoding_success").count(), 3
        )

    def test_geocoder_error_is_raised_and_nothing_is_flagged(self, mock_geocode):
        """
        Input: an obsolete address, the geocoder answers an HTTP error.
        Expected: the error is raised, the address keeps a null flag (it will be
        geocoded by the next run).
        """
        addr = self._obsolete_address("04001_old_00008", "place de la mairie")
        response = Mock(status_code=503)
        response.raise_for_status.side_effect = RuntimeError("503")
        mock_geocode.return_value = response

        with self.assertRaises(RuntimeError):
            geocode_obsolete_addresses()

        addr.refresh_from_db()
        self.assertIsNone(addr.ban_update_flag)


def _details(score, distance_m, street_rep=None, result_type="housenumber") -> dict:
    """Geocoding details of an obsolete address, as stored by
    geocode_obsolete_addresses, with only the fields the success rule reads."""
    return {
        "cle_interop": "04001_0040_00001",
        "type": result_type,
        "score": score,
        "distance_m": distance_m,
        "street_rep": street_rep,
    }


class TestIsGeocodingSuccess(TestCase):
    def test_distance_and_score_tiers(self):
        """
        Input: housenumber results without suffix on either side, on each side
        of the tiers (< 3 m whatever the score, < 20 m and > 0.55, < 50 m and
        > 0.7, < 150 m and > 0.85, < 300 m and > 0.9).
        Expected: a success only when one tier is met.
        """
        cases = [
            (0.3, 2, True),
            (0.3, 4, False),
            (0.6, 15, True),
            (0.5, 15, False),
            (0.75, 40, True),
            (0.65, 40, False),
            (0.88, 100, True),
            (0.8, 100, False),
            (0.95, 250, True),
            (0.88, 250, False),
            (0.99, 350, False),
        ]
        for score, distance_m, expected in cases:
            with self.subTest(score=score, distance_m=distance_m):
                self.assertEqual(
                    _is_geocoding_success(Address(), _details(score, distance_m)),
                    expected,
                )

    def test_not_a_housenumber_or_no_distance(self):
        """
        Input: a street result 0 m away with a 0.95 score, and a housenumber
        result with a 0.95 score but no distance (obsolete address without
        point).
        Expected: both are failures.
        """
        self.assertFalse(
            _is_geocoding_success(Address(), _details(0.95, 0, result_type="street"))
        )
        self.assertFalse(_is_geocoding_success(Address(), _details(0.95, None)))

    def test_suffix_on_one_side_only(self):
        """
        Input: results whose repetition index is present on one side only
        ("bis" lost, or "bis" added), at various scores and distances.
        Expected: a failure, unless < 10 m and score > 0.85.
        """
        cases = [
            ("bis", None, 0.95, 50, False),
            ("bis", None, 0.9, 5, True),
            ("bis", None, 0.8, 5, False),
            ("bis", None, 0.95, 15, False),
            (None, "bis", 0.95, 50, False),
        ]
        for old_rep, new_rep, score, distance_m, expected in cases:
            with self.subTest(old_rep=old_rep, new_rep=new_rep, score=score):
                self.assertEqual(
                    _is_geocoding_success(
                        Address(street_rep=old_rep),
                        _details(score, distance_m, street_rep=new_rep),
                    ),
                    expected,
                )

    def test_suffix_on_both_sides_or_null_string(self):
        """
        Input: "B" geocoded as "bis" 50 m away with a 0.9 score, and an obsolete
        address whose street_rep is the string "null" geocoded without suffix
        100 m away with a 0.9 score.
        Expected: both are successes ("B"/"bis" is a suffix on both sides,
        "null" is not a suffix).
        """
        self.assertTrue(
            _is_geocoding_success(
                Address(street_rep="B"), _details(0.9, 50, street_rep="bis")
            )
        )
        self.assertTrue(
            _is_geocoding_success(Address(street_rep="null"), _details(0.9, 100))
        )


class TestSplitHousenumber(TestCase):
    def test_split_housenumber(self):
        """
        Input: geocoder housenumbers "11B", "11 bis", "11", "" and None.
        Expected: ("11", "B"), ("11", "bis"), ("11", None), (None, None) and
        (None, None).
        """
        self.assertEqual(_split_housenumber("11B"), ("11", "B"))
        self.assertEqual(_split_housenumber("11 bis"), ("11", "bis"))
        self.assertEqual(_split_housenumber("11"), ("11", None))
        self.assertEqual(_split_housenumber(""), (None, None))
        self.assertEqual(_split_housenumber(None), (None, None))
