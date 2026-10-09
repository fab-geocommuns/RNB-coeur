from datetime import datetime
from typing import Optional
from unittest.mock import patch
from zoneinfo import ZoneInfo

import batid.tests.helpers as helpers
import requests
from batid.models import Address, City
from batid.services.imports.import_ban import (
    create_ban_full_import_tasks,
    has_city_reliable_ban_ids,
    import_ban_addresses,
    update_all_cities_ban_ids_reliability,
    update_dpt_cities_ban_ids_reliability,
    update_one_city_ban_ids_reliability,
)
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import TestCase


class BANImportDB(TestCase):
    @patch("batid.services.imports.import_ban.Source.find")
    def test_import_on_empty_db_one_batch(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        self.assertEqual(Address.objects.count(), 0)

        # Now UTC time
        before_import = datetime.now(ZoneInfo(settings.TIME_ZONE))

        import_ban_addresses({"dpt": "dummy"}, batch_size=100)

        self.assertEqual(Address.objects.count(), 4)

        # Verify the first address
        address = Address.objects.get(cle_interop="04001_pk624e_00001")

        self.assertEqual(address.source, "Import BAN")
        self.assertEqual(address.point, Point(6.135212, 44.070028, srid=4326))
        self.assertEqual(address.street_number, "1")
        self.assertEqual(address.street_rep, "bis")
        self.assertEqual(address.street, "Impasse de la Treille")
        self.assertEqual(address.city_name, "Aiglun")
        self.assertEqual(address.city_zipcode, "04510")
        self.assertEqual(address.city_insee_code, "04001")

        # We disabled id_ban import for now, so we expect ban_id to be None for all addresses
        # self.assertEqual(address.ban_id, UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"))
        self.assertEqual(address.ban_id, None)

        self.assertGreater(address.created_at, before_import)
        self.assertGreater(address.updated_at, before_import)

        # Verify an address without id_ban_adresse has ban_id=None
        address_without_ban_id = Address.objects.get(cle_interop="04001_pk624e_00003")
        self.assertIsNone(address_without_ban_id.ban_id)

    @patch("batid.services.imports.import_ban.Source.find")
    def test_import_on_empty_db_many_batches(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        self.assertEqual(Address.objects.count(), 0)

        import_ban_addresses({"dpt": "dummy"}, batch_size=1)

        self.assertEqual(Address.objects.count(), 4)

    @patch("batid.services.imports.import_ban.Source.find")
    def test_import_with_existing_addresses(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")

        # Create some addresse before import
        existing_address = Address.objects.create(
            cle_interop="04001_pk624e_00001",
            source="OldAddress",
            point=Point(0, 0, srid=4326),
            street_number="old_number",
            street_rep="old_rep",
            street="old_street",
            city_name="old_city",
            city_zipcode="00000",
            city_insee_code="11111",
        )
        old_created_at = existing_address.created_at
        old_updated_at = existing_address.updated_at

        self.assertEqual(Address.objects.count(), 1)

        import_ban_addresses({"dpt": "dummy"}, batch_size=100)

        self.assertEqual(Address.objects.count(), 4)

        # We verify the existing address has not been modified at all
        address = Address.objects.get(cle_interop="04001_pk624e_00001")

        self.assertEqual(address.source, "OldAddress")
        self.assertEqual(address.point, Point(0, 0, srid=4326))
        self.assertEqual(address.street_number, "old_number")
        self.assertEqual(address.street_rep, "old_rep")
        self.assertEqual(address.street, "old_street")
        self.assertEqual(address.city_name, "old_city")
        self.assertEqual(address.city_zipcode, "00000")
        self.assertEqual(address.city_insee_code, "11111")
        self.assertEqual(address.created_at, old_created_at)
        self.assertEqual(address.updated_at, old_updated_at)


def _ban_lookup_response(
    with_ban_id: Optional[bool], streets_sources: list, status_code=200
):
    """Build a fake response of the BAN lookup endpoint, with one "lieu-dit" (no sources) and one street per given sources list. The withBanId key is omitted when with_ban_id is None."""
    response = requests.Response()
    response.status_code = status_code
    voies = [{"type": "lieu-dit", "nomVoie": "Le Pré"}]
    voies += [{"type": "voie", "sources": sources} for sources in streets_sources]
    data: dict = {"voies": voies}
    if with_ban_id is not None:
        data["withBanId"] = with_ban_id
    response.json = lambda: data  # type: ignore[method-assign]
    return response


@patch("batid.services.imports.import_ban.BAN_LOOKUP_DELAY", 0)
@patch("batid.services.imports.import_ban.requests.get")
class BANIdsReliability(TestCase):
    def setUp(self):
        cache.clear()
        self.city = City.objects.create(code_insee="38185", name="Grenoble")

    def _reliability(self, insee_code="38185"):
        return City.objects.get(code_insee=insee_code).has_reliable_ban_ids

    def test_with_ban_id(self, get_mock):
        """Input: lookup with withBanId=true and "bal" streets. Expected: city becomes reliable, function returns True (changed)."""
        get_mock.return_value = _ban_lookup_response(True, [["bal"], ["bal"]])

        self.assertIsNone(self._reliability())
        changed, is_reliable = update_one_city_ban_ids_reliability("38185")

        self.assertTrue(changed)
        self.assertIs(is_reliable, True)
        self.assertIs(self._reliability(), True)
        get_mock.assert_called_once_with(
            "https://plateforme.adresse.data.gouv.fr/lookup/38185", timeout=30
        )

    def test_without_ban_id_no_bal(self, get_mock):
        """Input: lookup with withBanId=false and no "bal" street. Expected: city becomes reliable."""
        get_mock.return_value = _ban_lookup_response(
            False, [["cadastre", "ftth"], ["ign-api-gestion-ign"]]
        )

        update_one_city_ban_ids_reliability("38185")

        self.assertIs(self._reliability(), True)

    def test_without_ban_id_with_bal(self, get_mock):
        """Input: lookup with withBanId=false and "bal" streets. Expected: city becomes not reliable."""
        get_mock.return_value = _ban_lookup_response(False, [["bal"], ["bal"]])

        update_one_city_ban_ids_reliability("38185")

        self.assertIs(self._reliability(), False)

    def test_missing_ban_id_key_with_bal(self, get_mock):
        """Input: lookup without the withBanId key (old BAL without BAN IDs) and "bal" streets. Expected: no crash, city becomes not reliable."""
        get_mock.return_value = _ban_lookup_response(None, [["bal"], ["bal"]])

        update_one_city_ban_ids_reliability("38185")

        self.assertIs(self._reliability(), False)

    def test_unchanged_value_is_not_saved(self, get_mock):
        """Input: city already reliable, lookup says reliable. Expected: function returns False and the row is not updated."""
        City.objects.filter(code_insee="38185").update(has_reliable_ban_ids=True)
        updated_at = City.objects.get(code_insee="38185").updated_at
        get_mock.return_value = _ban_lookup_response(True, [["bal"]])

        changed, _ = update_one_city_ban_ids_reliability("38185")

        self.assertFalse(changed)
        self.assertEqual(City.objects.get(code_insee="38185").updated_at, updated_at)

    def test_districts_are_aggregated(self, get_mock):
        """Input: Lyon (69123), 8 reliable districts and one not reliable, then all reliable. Expected: one lookup per district, never on the city code; Lyon is not reliable, then reliable."""
        City.objects.create(code_insee="69123", name="Lyon")

        def lookup(url, timeout):
            if url.endswith("/69389"):
                return _ban_lookup_response(False, [["bal"]])
            return _ban_lookup_response(True, [["bal"]])

        get_mock.side_effect = lookup
        update_one_city_ban_ids_reliability("69123")

        self.assertIs(self._reliability("69123"), False)
        called_codes = [call.args[0].split("/")[-1] for call in get_mock.call_args_list]
        self.assertEqual(called_codes, [f"6938{i}" for i in range(1, 10)])

        get_mock.side_effect = None
        get_mock.return_value = _ban_lookup_response(True, [["bal"]])
        update_one_city_ban_ids_reliability("69123")

        self.assertIs(self._reliability("69123"), True)

    def test_update_dpt_only_checks_dpt_cities(self, get_mock):
        """Input: 2 cities in department 38 and one in department 01, lookups all reliable, update of department 38. Expected: only the 2 cities of department 38 are looked up and updated."""
        City.objects.create(code_insee="38001", name="A")
        City.objects.create(code_insee="01001", name="B")
        get_mock.return_value = _ban_lookup_response(True, [["bal"]])

        result = update_dpt_cities_ban_ids_reliability("38")

        self.assertIs(self._reliability("38001"), True)
        self.assertIs(self._reliability("38185"), True)
        self.assertIsNone(self._reliability("01001"))
        called_codes = [call.args[0].split("/")[-1] for call in get_mock.call_args_list]
        self.assertEqual(called_codes, ["38001", "38185"])
        self.assertEqual(
            result,
            "[38] BAN IDs reliability: 2 cities checked, 2 changed, 0 unverifiable",
        )

    def test_unknown_city_is_unverifiable(self, get_mock):
        """Input: city reliable in db, lookup returns a 404 (city unknown to the BAN, eg: merged into another one). Expected: city reliability is reset to None, function returns (True, None)."""
        City.objects.filter(code_insee="38185").update(has_reliable_ban_ids=True)
        get_mock.return_value = _ban_lookup_response(False, [], status_code=404)

        changed, is_reliable = update_one_city_ban_ids_reliability("38185")

        self.assertTrue(changed)
        self.assertIsNone(is_reliable)
        self.assertIsNone(self._reliability())

    def test_unknown_district_makes_city_unverifiable(self, get_mock):
        """Input: Lyon (69123) reliable in db, lookup returns a 404 for one district and reliable for the others. Expected: Lyon reliability is reset to None."""
        City.objects.create(code_insee="69123", name="Lyon", has_reliable_ban_ids=True)

        def lookup(url, timeout):
            if url.endswith("/69385"):
                return _ban_lookup_response(False, [], status_code=404)
            return _ban_lookup_response(True, [["bal"]])

        get_mock.side_effect = lookup
        update_one_city_ban_ids_reliability("69123")

        self.assertIsNone(self._reliability("69123"))

    def test_update_dpt_skips_unknown_cities(self, get_mock):
        """Input: 3 cities in department 01, the second one is reliable in db and unknown to the BAN (404), the others are reliable. Expected: no error, the process goes on; the unknown city is set to None and counted as unverifiable."""
        City.objects.create(code_insee="01001", name="A")
        City.objects.create(
            code_insee="01330", name="Ruffieu", has_reliable_ban_ids=True
        )
        City.objects.create(code_insee="01400", name="C")

        def lookup(url, timeout):
            if url.endswith("/01330"):
                return _ban_lookup_response(False, [], status_code=404)
            return _ban_lookup_response(True, [["bal"]])

        get_mock.side_effect = lookup

        result = update_dpt_cities_ban_ids_reliability("01")

        self.assertIs(self._reliability("01001"), True)
        self.assertIsNone(self._reliability("01330"))
        self.assertIs(self._reliability("01400"), True)
        self.assertEqual(
            result,
            "[01] BAN IDs reliability: 3 cities checked, 3 changed, 1 unverifiable",
        )

    def test_update_dpt_crashes_on_failure(self, get_mock):
        """Input: 2 cities in department 01; lookup is reliable for the first one and a 500 for the second. Expected: an HTTPError is raised; the first city is updated, the second keeps its value."""
        City.objects.create(code_insee="01001", name="A")
        City.objects.create(code_insee="01002", name="B", has_reliable_ban_ids=False)

        def lookup(url, timeout):
            if url.endswith("/01002"):
                return _ban_lookup_response(False, [], status_code=500)
            return _ban_lookup_response(True, [["bal"]])

        get_mock.side_effect = lookup

        with self.assertRaises(requests.HTTPError):
            update_dpt_cities_ban_ids_reliability("01")

        self.assertIs(self._reliability("01001"), True)
        self.assertIs(self._reliability("01002"), False)

    def test_update_all_dpts(self, get_mock):
        """Input: cities in departments 01, 2A, 38 and 971, lookups all reliable, update of all departments. Expected: every city is looked up (in departments order) and updated; the result sums all departments."""
        City.objects.create(code_insee="01001", name="A")
        City.objects.create(code_insee="2A004", name="Ajaccio")
        City.objects.create(code_insee="97101", name="B")
        get_mock.return_value = _ban_lookup_response(True, [["bal"]])

        result = update_all_cities_ban_ids_reliability()

        for insee_code in ["01001", "2A004", "38185", "97101"]:
            self.assertIs(self._reliability(insee_code), True)
        called_codes = [call.args[0].split("/")[-1] for call in get_mock.call_args_list]
        self.assertEqual(called_codes, ["01001", "2A004", "38185", "97101"])
        self.assertEqual(
            result,
            "[01 to 989] BAN IDs reliability: 4 cities checked, 4 changed, "
            "0 unverifiable",
        )

    def test_update_all_dpts_from_start_to_end(self, get_mock):
        """Input: cities in departments 01, 2A, 38 and 971, lookups all reliable, update from department 2A to 38. Expected: only the cities of 2A and 38 are looked up and updated."""
        City.objects.create(code_insee="01001", name="A")
        City.objects.create(code_insee="2A004", name="Ajaccio")
        City.objects.create(code_insee="97101", name="B")
        get_mock.return_value = _ban_lookup_response(True, [["bal"]])

        result = update_all_cities_ban_ids_reliability(dpt_start="2A", dpt_end="38")

        self.assertIsNone(self._reliability("01001"))
        self.assertIsNone(self._reliability("97101"))
        called_codes = [call.args[0].split("/")[-1] for call in get_mock.call_args_list]
        self.assertEqual(called_codes, ["2A004", "38185"])
        self.assertEqual(
            result,
            "[2A to 38] BAN IDs reliability: 2 cities checked, 2 changed, "
            "0 unverifiable",
        )

    def test_has_city_reliable_ban_ids(self, get_mock):
        """Input: a reliable city, a not reliable one, a never checked one, an unknown code, a district of reliable Paris. Expected: True only for the reliable city and the Paris district."""
        City.objects.filter(code_insee="38185").update(has_reliable_ban_ids=True)
        City.objects.create(code_insee="01001", name="A", has_reliable_ban_ids=False)
        City.objects.create(code_insee="01002", name="B")
        City.objects.create(code_insee="75056", name="Paris", has_reliable_ban_ids=True)

        self.assertIs(has_city_reliable_ban_ids("38185"), True)
        self.assertIs(has_city_reliable_ban_ids("01001"), False)
        self.assertIs(has_city_reliable_ban_ids("01002"), False)
        self.assertIs(has_city_reliable_ban_ids("99999"), False)
        self.assertIs(has_city_reliable_ban_ids("75101"), True)

    def test_has_city_reliable_ban_ids_is_cached(self, get_mock):
        """Input: two calls for the same city, the column being changed in between without going through the update function. Expected: second call does no query and returns the cached value, with a 10 minutes timeout."""
        City.objects.filter(code_insee="38185").update(has_reliable_ban_ids=True)

        with patch(
            "batid.services.imports.import_ban.cache.set", wraps=cache.set
        ) as set_mock:
            self.assertIs(has_city_reliable_ban_ids("38185"), True)
            self.assertEqual(set_mock.call_args.kwargs["timeout"], 600)

        City.objects.filter(code_insee="38185").update(has_reliable_ban_ids=False)

        with self.assertNumQueries(0):
            self.assertIs(has_city_reliable_ban_ids("38185"), True)

    def test_update_invalidates_cache(self, get_mock):
        """Input: cached reliable city, then update_one_city_ban_ids_reliability makes it not reliable. Expected: has_city_reliable_ban_ids returns False right away."""
        City.objects.filter(code_insee="38185").update(has_reliable_ban_ids=True)
        self.assertIs(has_city_reliable_ban_ids("38185"), True)

        get_mock.return_value = _ban_lookup_response(False, [["bal"]])
        update_one_city_ban_ids_reliability("38185")

        self.assertIs(has_city_reliable_ban_ids("38185"), False)


class BANImportTasks(TestCase):
    def test_reliability_task_for_each_dpt(self):
        """Input: full BAN import tasks for 2 departments. Expected: for each department, a reliability task (with the department as argument), then download, then import."""
        tasks = create_ban_full_import_tasks(["01", "02"])

        self.assertEqual(
            [t.task for t in tasks],
            [
                "batid.tasks.update_dpt_cities_ban_ids_reliability",
                "batid.tasks.dl_source",
                "batid.tasks.import_ban",
                "batid.tasks.update_dpt_cities_ban_ids_reliability",
                "batid.tasks.dl_source",
                "batid.tasks.import_ban",
            ],
        )
        self.assertEqual(tasks[0].args, ("01",))
        self.assertEqual(tasks[3].args, ("02",))
