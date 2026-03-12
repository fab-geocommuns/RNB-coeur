from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import UUID

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.test import TransactionTestCase

import batid.tests.helpers as helpers
from batid.models import Address
from batid.models import BuildingAddressesReadOnly
from batid.models import BuildingHistoryOnly
from batid.services.imports.update_addresses_ban import _expand_street_abbreviations
from batid.services.imports.update_addresses_ban import _mark_existing_addresses
from batid.services.imports.update_addresses_ban import _streets_match
from batid.services.imports.update_addresses_ban import (
    delete_unlinked_obsolete_addresses,
)
from batid.services.imports.update_addresses_ban import flag_addresses_from_ban_file
from batid.services.imports.update_addresses_ban import (
    geocode_and_update_obsolete_addresses,
)
from batid.services.imports.update_addresses_ban import normalize_text
from batid.services.imports.update_addresses_ban import (
    update_addresses_text_and_ban_id,
)


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


class TestUpdateAddressesTextAndBanId(TestCase):
    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_matching_text_updates_street_city_and_ban_id(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Fixture row 1: numero=1, rep=bis, nom_voie=Impasse de la Treille,
        # code_postal=04510, code_insee=04001, nom_commune=Aiglun,
        # lon=6.135212, lat=44.070028
        # id_ban_adresse=a1b2c3d4-e5f6-7890-abcd-ef1234567890
        # Point ~5m from BAN coordinates
        Address.objects.create(
            id="04001_pk624e_00001",
            source="ban",
            still_exists=True,
            point=Point(6.13518, 44.07000, srid=4326),
            street="impasse de la treille",
            street_number="1",
            # test de l'alias B / bis
            street_rep="B",  # alias for "bis" in BAN fixture
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )
        # Fixture row 2: nom_voie=Impasse de la Treille
        # DB has abbreviation "Imp" → should match via alias expansion
        Address.objects.create(
            id="04001_pk624e_00002",
            source="ban",
            still_exists=True,
            street="Imp de la Treille",
            street_number="2",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )
        # Fixture row 3: nom_voie=Impasse de la Treille
        # DB has "Impasse de las Treilles" (Levenshtein distance = 2) → should match
        Address.objects.create(
            id="04001_pk624e_00003",
            source="ban",
            still_exists=True,
            street="Impasse de las Treilles",
            street_number="3",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["updated"], 3)
        self.assertEqual(result["mismatched"], 0)

        # Row 1: exact match (after normalization)
        addr = Address.objects.get(id="04001_pk624e_00001")
        self.assertEqual(addr.street, "Impasse de la Treille")
        self.assertEqual(addr.city_name, "Aiglun")
        self.assertEqual(addr.street_rep, "bis")
        self.assertEqual(addr.ban_id, UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"))
        self.assertEqual(addr.ban_update_flag, "update")
        self.assertIsNone(addr.ban_update_details)
        # Point should be updated to BAN coordinates
        self.assertAlmostEqual(addr.point.x, 6.135212, places=5)
        self.assertAlmostEqual(addr.point.y, 44.070028, places=5)

        # Row 2: abbreviation "Imp" expanded to "impasse" → match
        addr2 = Address.objects.get(id="04001_pk624e_00002")
        self.assertEqual(addr2.street, "Impasse de la Treille")
        self.assertEqual(addr2.ban_update_flag, "update")

        # Row 3: Levenshtein distance = 2 → match
        addr3 = Address.objects.get(id="04001_pk624e_00003")
        self.assertEqual(addr3.street, "Impasse de la Treille")
        self.assertEqual(addr3.ban_update_flag, "update")

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_mismatching_text_no_point_flags_mismatch_without_distance(
        self, mock_remove, mock_find
    ):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # DB has "rue de la gare" but BAN has "Impasse de la Treille" → mismatch
        # No point → distance_m should not appear in details
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
        # Details should contain the mismatched field but no distance
        self.assertIn("street", addr.ban_update_details)
        self.assertEqual(addr.ban_update_details["street"]["db"], "rue de la gare")
        self.assertEqual(
            addr.ban_update_details["street"]["ban"], "Impasse de la Treille"
        )
        self.assertNotIn("distance_m", addr.ban_update_details)

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

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_close_distance_updates_despite_field_diffs(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Fixture row 2: lon=6.135332, lat=44.069986, nom_voie=Impasse de la Treille
        # DB street differs, but point is ~5m away → distance < 20m → update
        Address.objects.create(
            id="04001_pk624e_00002",
            source="ban",
            still_exists=True,
            point=Point(6.13530, 44.06996, srid=4326),
            street="rue de la gare",
            street_number="2",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["mismatched"], 0)

        addr = Address.objects.get(id="04001_pk624e_00002")
        self.assertEqual(addr.ban_update_flag, "update")
        # Fields should be updated to BAN values
        self.assertEqual(addr.street, "Impasse de la Treille")
        self.assertEqual(addr.ban_id, UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901"))
        # Point should be updated to BAN coordinates
        self.assertAlmostEqual(addr.point.x, 6.135332, places=5)
        self.assertAlmostEqual(addr.point.y, 44.069986, places=5)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_far_distance_with_matching_fields_updates(self, mock_remove, mock_find):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Fixture row 1: lon=6.135212, lat=44.070028
        # Point is ~500m away but all fields match → update
        Address.objects.create(
            id="04001_pk624e_00001",
            source="ban",
            still_exists=True,
            point=Point(6.14, 44.073, srid=4326),
            street="impasse de la treille",
            street_number="1",
            street_rep="B",
            city_name="aiglun",
            city_zipcode="04510",
            city_insee_code="04001",
        )

        result = update_addresses_text_and_ban_id({"dpt": "04"})

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["mismatched"], 0)

        addr = Address.objects.get(id="04001_pk624e_00001")
        self.assertEqual(addr.ban_update_flag, "update")
        self.assertEqual(addr.street, "Impasse de la Treille")
        # Point should be updated to BAN coordinates
        self.assertAlmostEqual(addr.point.x, 6.135212, places=5)
        self.assertAlmostEqual(addr.point.y, 44.070028, places=5)

    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_far_distance_with_field_diffs_flags_mismatch_with_distance(
        self, mock_remove, mock_find
    ):
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Fixture row 2: lon=6.135332, lat=44.069986, nom_voie=Impasse de la Treille
        # Point is ~500m away AND street differs → mismatch with distance_m
        Address.objects.create(
            id="04001_pk624e_00002",
            source="ban",
            still_exists=True,
            point=Point(6.14, 44.073, srid=4326),
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
        self.assertEqual(addr.street, "rue de la gare")
        self.assertIn("street", addr.ban_update_details)
        # Distance should be present and > 20m
        self.assertIn("distance_m", addr.ban_update_details)
        self.assertGreater(addr.ban_update_details["distance_m"], 15)


class TestUpdateAddressesTextAndBanIdDuplicateBanId(TestCase):
    @patch("batid.services.imports.update_addresses_ban.Source.find")
    @patch("batid.services.imports.update_addresses_ban.os.remove")
    def test_duplicate_ban_id_second_row_is_skipped(self, _mock_remove, mock_find):
        """
        This test exists because unfortunately we can have BAN files with duplicated ban_ids.
        """
        mock_find.return_value = helpers.fixture_path(
            "ban_with_ids_duplicate_ban_id.csv"
        )

        # Two addresses in DB, both present in the fixture with the same id_ban_adresse
        Address.objects.create(
            id="85288_p1h9zg_02965",
            source="ban",
            still_exists=True,
            street="route de la martiniere",
            street_number="2965",
            city_name="talmont-saint-hilaire",
            city_zipcode="85440",
            city_insee_code="85288",
        )
        Address.objects.create(
            id="85103_0099_02965",
            source="ban",
            still_exists=True,
            street="route de la martiniere",
            street_number="2965",
            city_name="grosbreuil",
            city_zipcode="85440",
            city_insee_code="85103",
        )

        result = update_addresses_text_and_ban_id({"dpt": "85"})

        # Only the first row is processed; the second (duplicate ban_id) is skipped
        self.assertEqual(result["updated"], 1)

        addr1 = Address.objects.get(id="85288_p1h9zg_02965")
        self.assertEqual(addr1.ban_id, UUID("9e63d301-1c76-4d33-a508-9ea9e39293d2"))
        self.assertEqual(addr1.ban_update_flag, "update")

        # Second address was skipped entirely: no ban_id, no update flag
        addr2 = Address.objects.get(id="85103_0099_02965")
        self.assertIsNone(addr2.ban_id)
        self.assertIsNone(addr2.ban_update_flag)


class TestGeocodeAndUpdateObsoleteAddresses(TransactionTestCase):
    def _make_geocoder_response(self, rows):
        """Build a mock geocoder response with a CSV body."""
        header = "db_id,numero,voie,postcode,city,citycode,result_id,result_score,result_type"
        lines = [header] + [
            f"{r['db_id']},,,,,,"
            f"{r.get('result_id', '')},"
            f"{r.get('result_score', '')},"
            f"{r.get('result_type', '')}"
            for r in rows
        ]
        mock_resp = MagicMock()
        mock_resp.text = "\n".join(lines)
        return mock_resp

    def _create_linked_obsolete_address(self, addr_id, bdg_rnb_id="BDG1"):
        addr = Address.objects.create(
            id=addr_id,
            source="ban",
            still_exists=False,
            street_number="1",
            street="Rue de la Paix",
            city_zipcode="04510",
            city_name="Aiglun",
            city_insee_code="04001",
        )
        bdg = helpers.create_default_bdg(bdg_rnb_id)
        bdg.addresses_id = [addr_id]
        bdg.save()
        return addr, bdg

    def test_good_score_housenumber_updates_pk_and_buildings(self):
        """
        Input: obsolete address linked to a building, geocoder returns score=0.9, type=housenumber,
               new cle_interop=04001_new_00001.
        Expected: Address.id updated to new value, still_exists=True, ban_update_flag=None,
                  text fields unchanged (will be updated by update_addresses_text_and_ban_id),
                  Building.addresses_id updated, BuildingAddressesReadOnly synchronized.
        """
        addr, bdg = self._create_linked_obsolete_address("04001_old_00001", "BDG1")

        mock_resp = self._make_geocoder_response(
            [
                {
                    "db_id": "04001_old_00001",
                    "result_id": "04001_new_00001",
                    "result_score": "0.9",
                    "result_type": "housenumber",
                }
            ]
        )

        with patch(
            "batid.services.imports.update_addresses_ban.BanBatchGeocoder"
        ) as MockGeocoder:
            MockGeocoder.return_value.geocode.return_value = mock_resp
            result = geocode_and_update_obsolete_addresses()

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["geocoding_failures"], 0)

        self.assertFalse(Address.objects.filter(id="04001_old_00001").exists())
        addr_new = Address.objects.get(id="04001_new_00001")
        self.assertTrue(addr_new.still_exists)
        self.assertIsNone(addr_new.ban_update_flag)
        # Text fields are not updated here — update_addresses_text_and_ban_id handles that
        self.assertEqual(addr_new.street, "Rue de la Paix")
        self.assertEqual(addr_new.street_number, "1")
        self.assertEqual(addr_new.city_name, "Aiglun")

        bdg.refresh_from_db()
        self.assertIn("04001_new_00001", bdg.addresses_id)
        self.assertNotIn("04001_old_00001", bdg.addresses_id)

        self.assertTrue(
            BuildingAddressesReadOnly.objects.filter(
                building=bdg, address_id="04001_new_00001"
            ).exists()
        )

        self.assertFalse(
            BuildingAddressesReadOnly.objects.filter(
                building=bdg, address_id="04001_old_00001"
            ).exists()
        )

    def test_bad_score_flags_not_found(self):
        """
        Input: obsolete address linked to building, geocoder returns score=0.5 (below threshold).
        Expected: ban_update_flag='not_found', still_exists=False unchanged, Address.id unchanged.
        """
        addr, bdg = self._create_linked_obsolete_address("04001_old_00002", "BDG2")

        mock_resp = self._make_geocoder_response(
            [
                {
                    "db_id": "04001_old_00002",
                    "result_id": "04001_new_00002",
                    "result_score": "0.5",
                    "result_type": "housenumber",
                }
            ]
        )

        with patch(
            "batid.services.imports.update_addresses_ban.BanBatchGeocoder"
        ) as MockGeocoder:
            MockGeocoder.return_value.geocode.return_value = mock_resp
            result = geocode_and_update_obsolete_addresses()

        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["geocoding_failures"], 1)

        addr.refresh_from_db()
        self.assertFalse(addr.still_exists)
        self.assertEqual(addr.ban_update_flag, "geocoding_failure")
        self.assertTrue(Address.objects.filter(id="04001_old_00002").exists())

    def test_non_housenumber_type_flags_not_found(self):
        """
        Input: obsolete address linked to building, geocoder returns score=0.9 but type='street'.
        Expected: ban_update_flag='not_found', Address.id unchanged.
        """
        addr, bdg = self._create_linked_obsolete_address("04001_old_00003", "BDG3")

        mock_resp = self._make_geocoder_response(
            [
                {
                    "db_id": "04001_old_00003",
                    "result_id": "04001_new_00003",
                    "result_score": "0.9",
                    "result_type": "street",
                }
            ]
        )

        with patch(
            "batid.services.imports.update_addresses_ban.BanBatchGeocoder"
        ) as MockGeocoder:
            MockGeocoder.return_value.geocode.return_value = mock_resp
            result = geocode_and_update_obsolete_addresses()

        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["geocoding_failures"], 1)

        addr.refresh_from_db()
        self.assertFalse(addr.still_exists)
        self.assertEqual(addr.ban_update_flag, "geocoding_failure")
        self.assertEqual(
            addr.ban_update_details, {"new_id": "04001_new_00003", "score": 0.9}
        )

    def test_versioning_trigger_not_fired_during_update(self):
        """
        Input: obsolete address linked to building, geocoder returns good result.
        Expected: no new entry in batid_building_history after the PK update
                  (versioning trigger is disabled during the operation).
        """
        addr, bdg = self._create_linked_obsolete_address("04001_old_00004", "BDG4")

        history_count_before = BuildingHistoryOnly.objects.filter(
            rnb_id=bdg.rnb_id
        ).count()

        mock_resp = self._make_geocoder_response(
            [
                {
                    "db_id": "04001_old_00004",
                    "result_id": "04001_new_00004",
                    "result_score": "0.9",
                    "result_type": "housenumber",
                }
            ]
        )

        with patch(
            "batid.services.imports.update_addresses_ban.BanBatchGeocoder"
        ) as MockGeocoder:
            MockGeocoder.return_value.geocode.return_value = mock_resp
            geocode_and_update_obsolete_addresses()

        history_count_after = BuildingHistoryOnly.objects.filter(
            rnb_id=bdg.rnb_id
        ).count()

        self.assertEqual(history_count_before, history_count_after)

    def test_building_history_addresses_id_updated(self):
        """
        Input: obsolete address linked to a building; the building is saved twice
               (two status changes) producing two history entries both referencing the old address.
               Geocoder returns score=0.9, type=housenumber, new cle_interop=04001_new_00005.
        Expected: all BuildingHistoryOnly entries referencing the old address ID are updated
                  to reference the new address ID (both versions).
        """
        addr, bdg = self._create_linked_obsolete_address("04001_old_00005", "BDG5")

        # Second save: change status to produce a second history entry still referencing old address
        bdg.status = "demolished"
        bdg.save()
        bdg.status = "constructed"
        bdg.save()

        history_with_old = BuildingHistoryOnly.objects.filter(
            rnb_id=bdg.rnb_id,
            addresses_id__contains=["04001_old_00005"],
        )
        self.assertGreaterEqual(history_with_old.count(), 2)

        mock_resp = self._make_geocoder_response(
            [
                {
                    "db_id": "04001_old_00005",
                    "result_id": "04001_new_00005",
                    "result_score": "0.9",
                    "result_type": "housenumber",
                }
            ]
        )

        with patch(
            "batid.services.imports.update_addresses_ban.BanBatchGeocoder"
        ) as MockGeocoder:
            MockGeocoder.return_value.geocode.return_value = mock_resp
            geocode_and_update_obsolete_addresses()

        # No history entry should still reference the old address
        self.assertFalse(
            BuildingHistoryOnly.objects.filter(
                rnb_id=bdg.rnb_id,
                addresses_id__contains=["04001_old_00005"],
            ).exists()
        )
        # All formerly-referencing entries should now reference the new address
        self.assertGreaterEqual(
            BuildingHistoryOnly.objects.filter(
                rnb_id=bdg.rnb_id,
                addresses_id__contains=["04001_new_00005"],
            ).count(),
            2,
        )

    def test_geocoder_returns_existing_key_marks_old_for_delete(self):
        """
        Input: interop_1 (still_exists=True) and interop_2 (still_exists=False) linked to a building.
               Geocoder returns that interop_2's address now has key interop_1 (already in DB).
        Expected: building re-linked to interop_1, interop_2 marked with ban_update_flag='mark_for_delete'.
        """
        Address.objects.create(
            id="04001_interop_00001",
            source="ban",
            still_exists=True,
            street_number="1",
            street="Rue de la Paix",
            city_zipcode="04510",
            city_name="Aiglun",
            city_insee_code="04001",
        )
        addr2, bdg = self._create_linked_obsolete_address("04001_interop_00002", "BDG6")

        bdg.status = "demolished"
        bdg.save()

        bdg_history = BuildingHistoryOnly.objects.filter(rnb_id=bdg.rnb_id).order_by(
            "id"
        )
        # _create_linked_obsolete_address creates a first history version
        # status change creates a second one.
        self.assertEqual(len(bdg_history), 2)
        bdg_history = bdg_history[1]

        # the old key is in the addresses array
        self.assertEqual(bdg_history.addresses_id, ["04001_interop_00002"])

        mock_resp = self._make_geocoder_response(
            [
                {
                    "db_id": "04001_interop_00002",
                    "result_id": "04001_interop_00001",
                    "result_score": "0.9",
                    "result_type": "housenumber",
                }
            ]
        )

        with patch(
            "batid.services.imports.update_addresses_ban.BanBatchGeocoder"
        ) as MockGeocoder:
            MockGeocoder.return_value.geocode.return_value = mock_resp
            geocode_and_update_obsolete_addresses()

        bdg.refresh_from_db()
        self.assertIn("04001_interop_00001", bdg.addresses_id)
        self.assertNotIn("04001_interop_00002", bdg.addresses_id)

        addr2.refresh_from_db()
        self.assertEqual(addr2.ban_update_flag, "mark_for_delete")

        bdg_history.refresh_from_db()
        # the old key has been replaced by the new one
        self.assertEqual(bdg_history.addresses_id, ["04001_interop_00001"])


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
