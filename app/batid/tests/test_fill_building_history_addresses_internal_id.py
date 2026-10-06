from batid.models import Address, Building, BuildingHistoryOnly
from batid.services.data_fix.fill_building_history_addresses_internal_id import (
    fill_building_history_addresses_internal_id,
)
from django.db import connection
from django.test import TestCase


def read_address_internal_id_by_cle() -> dict:
    """Read batid_address.internal_id straight from the database, keyed by the
    "clé d'interopérabilité" (batid_address.id)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, internal_id FROM batid_address;")
        return dict(cursor.fetchall())


def read_history_addresses_internal_id() -> dict:
    """Read batid_building_history.addresses_internal_id straight from the
    database, keyed by rnb_id. Assumes at most one history row per rnb_id, as
    every test in this file only historicizes a building once."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rnb_id, addresses_internal_id FROM batid_building_history;"
        )
        return dict(cursor.fetchall())


def historicize(rnb_id: str, addresses_id) -> BuildingHistoryOnly:
    """Create a Building with the given addresses_id, then change and save it
    so that its pre-change state (including addresses_id) is pushed into
    batid_building_history by the versioning trigger. Returns the resulting
    history row."""
    building = Building.objects.create(rnb_id=rnb_id, addresses_id=addresses_id)
    building.parent_buildings = [1]
    building.save()
    return BuildingHistoryOnly.objects.get(rnb_id=rnb_id)


class FillBuildingHistoryAddressesInternalIdTestCase(TestCase):
    """Backfill of history rows written before addresses_internal_id started
    being populated (this column has never been written by application code
    for batid_building_history, only PR 4's double-write on batid_building)."""

    def setUp(self):
        for cle in [
            "00000_0000_00001",
            "00000_0000_00002",
            "00000_0000_00003",
        ]:
            Address.objects.create(id=cle, source="ban")
        self.internal_id_by_cle = read_address_internal_id_by_cle()

        self.history_two_addresses = historicize(
            "BDG00000001", ["00000_0000_00001", "00000_0000_00002"]
        )
        self.history_one_address = historicize("BDG00000002", ["00000_0000_00003"])
        self.history_no_address = historicize("BDG00000003", [])
        self.history_null_addresses_id = historicize("BDG00000004", None)

    def test_fills_every_empty_row_in_addresses_id_order(self):
        """Input: four history rows with addresses_internal_id NULL, batch_size=2
        so the backfill runs over several batches.
        Expected: every row whose addresses_id is not NULL gets its mirror
        array, values in the same order as addresses_id; the NULL one is left
        NULL."""
        updated = fill_building_history_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 3)
        rows = read_history_addresses_internal_id()
        self.assertEqual(
            rows["BDG00000001"],
            [
                self.internal_id_by_cle["00000_0000_00001"],
                self.internal_id_by_cle["00000_0000_00002"],
            ],
        )
        self.assertEqual(
            rows["BDG00000002"], [self.internal_id_by_cle["00000_0000_00003"]]
        )
        self.assertEqual(rows["BDG00000003"], [])
        self.assertIsNone(rows["BDG00000004"])

    def test_min_id_max_id_restrict_the_range(self):
        """Input: the backfill run twice with disjoint, complementary
        min_id/max_id ranges over bh_id (as two parallel workers would).
        Expected: together they fill every eligible history row exactly once,
        the same result as a single unrestricted run."""
        boundary = self.history_two_addresses.bh_id

        updated_first_half = fill_building_history_addresses_internal_id(
            batch_size=2, max_id=boundary
        )
        updated_second_half = fill_building_history_addresses_internal_id(
            batch_size=2, min_id=boundary
        )

        self.assertEqual(updated_first_half, 1)
        self.assertEqual(updated_second_half, 2)
        rows = read_history_addresses_internal_id()
        self.assertEqual(
            rows["BDG00000001"],
            [
                self.internal_id_by_cle["00000_0000_00001"],
                self.internal_id_by_cle["00000_0000_00002"],
            ],
        )
        self.assertEqual(
            rows["BDG00000002"], [self.internal_id_by_cle["00000_0000_00003"]]
        )
        self.assertEqual(rows["BDG00000003"], [])

    def test_does_not_overwrite_existing_values(self):
        """Input: one history row already filled, with a value that
        deliberately does not match its addresses_id, three others still NULL.
        Expected: only the three NULL ones are touched, the pre-filled one
        keeps its exact (mismatched) value untouched."""
        already_filled = [self.internal_id_by_cle["00000_0000_00003"]]
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE batid_building_history SET addresses_internal_id = %s WHERE rnb_id = %s;",
                [already_filled, "BDG00000001"],
            )

        updated = fill_building_history_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 2)
        rows = read_history_addresses_internal_id()
        self.assertEqual(rows["BDG00000001"], already_filled)

    def test_is_idempotent(self):
        """Running the backfill a second time updates nothing and changes nothing."""
        fill_building_history_addresses_internal_id(batch_size=2)
        after_first_run = read_history_addresses_internal_id()

        updated = fill_building_history_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 0)
        self.assertEqual(read_history_addresses_internal_id(), after_first_run)

    def test_orphan_cle_becomes_positional_null(self):
        """Input: a history row whose addresses_id contains one cle resolvable
        to a batid_address row and one that is not (simulating a history row
        written before migration 0125, referencing an address since deleted -
        unreachable through normal writes today, so built here with a raw SQL
        UPDATE of addresses_id after historicization).
        Expected: the resolvable cle's internal_id is filled at its position,
        the orphan cle's position is NULL, the array keeps addresses_id's
        length and order, and the run does not raise."""
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE batid_building_history SET addresses_id = %s WHERE rnb_id = %s;",
                [["00000_0000_00001", "orphan_cle"], "BDG00000001"],
            )

        updated = fill_building_history_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 3)
        rows = read_history_addresses_internal_id()
        self.assertEqual(
            rows["BDG00000001"],
            [self.internal_id_by_cle["00000_0000_00001"], None],
        )

    def test_no_join_table_side_effect(self):
        """Input: history rows backfilled through a raw UPDATE of
        addresses_internal_id.
        Expected: unlike the batid_building backfill, this leaves
        batid_buildingaddressesinternalidreadonly untouched, since
        keep_building_address_link_updated() is attached to batid_building
        only, not batid_building_history."""
        fill_building_history_addresses_internal_id(batch_size=2)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM batid_buildingaddressesinternalidreadonly;"
            )
            self.assertEqual(cursor.fetchone()[0], 0)


class FillBuildingHistoryAddressesInternalIdEmptyTableTestCase(TestCase):
    """Separate from FillBuildingHistoryAddressesInternalIdTestCase, which
    always historicizes a few buildings in setUp: history rows can only be
    created by the versioning trigger reacting to a Building write, and can
    never be deleted (prevent_delete_building_history_trigger), so this is
    the only way to exercise a genuinely empty table."""

    def test_on_empty_table(self):
        """No history row at all -> the backfill returns 0 instead of looping."""
        self.assertEqual(fill_building_history_addresses_internal_id(batch_size=2), 0)
