from batid.models import (
    Address,
    Building,
    BuildingAddressesInternalIdReadOnly,
    BuildingHistoryOnly,
)
from batid.services.data_fix.fill_building_addresses_internal_id import (
    fill_building_addresses_internal_id,
)
from django.db import connection
from django.test import TestCase


def read_building_addresses_internal_id() -> dict:
    """Read batid_building.addresses_internal_id straight from the database,
    keyed by rnb_id."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT rnb_id, addresses_internal_id FROM batid_building;")
        return dict(cursor.fetchall())


def read_address_internal_id_by_cle() -> dict:
    """Read batid_address.internal_id straight from the database, keyed by the
    "clé d'interopérabilité" (batid_address.id)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, internal_id FROM batid_address;")
        return dict(cursor.fetchall())


def history_count(rnb_id):
    return BuildingHistoryOnly.objects.filter(rnb_id=rnb_id).count()


class FillBuildingAddressesInternalIdTestCase(TestCase):
    """Backfill of the buildings written before Building._dangerously_save_forever()
    started mirroring addresses_id into addresses_internal_id (PR #1029)."""

    def setUp(self):
        for cle in [
            "00000_0000_00001",
            "00000_0000_00002",
            "00000_0000_00003",
        ]:
            Address.objects.create(id=cle, source="ban")
        self.internal_id_by_cle = read_address_internal_id_by_cle()

        # Created through the ORM directly (bypassing
        # Building._dangerously_save_forever()), so addresses_internal_id stays
        # NULL exactly as it would for a row written before PR #1029.
        self.building_two_addresses = Building.objects.create(
            rnb_id="BDG00000001",
            addresses_id=["00000_0000_00001", "00000_0000_00002"],
        )
        self.building_one_address = Building.objects.create(
            rnb_id="BDG00000002", addresses_id=["00000_0000_00003"]
        )
        self.building_no_address = Building.objects.create(
            rnb_id="BDG00000003", addresses_id=[]
        )
        self.building_null_addresses_id = Building.objects.create(
            rnb_id="BDG00000004", addresses_id=None
        )

    def test_fills_every_empty_row_in_addresses_id_order(self):
        """Input: four buildings with addresses_internal_id NULL, batch_size=2 so
        the backfill runs over several batches.
        Expected: every building whose addresses_id is not NULL gets its mirror
        array, values in the same order as addresses_id; the NULL one is left
        NULL."""
        updated = fill_building_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 3)
        rows = read_building_addresses_internal_id()
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

    def test_does_not_overwrite_existing_values(self):
        """Input: one building already filled (as PR #1029's write path would do),
        with a value that deliberately does not match its addresses_id, three
        others still NULL.
        Expected: only the three NULL ones are touched, the pre-filled one keeps
        its exact (mismatched) value untouched."""
        already_filled = [self.internal_id_by_cle["00000_0000_00003"]]
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE batid_building SET addresses_internal_id = %s WHERE rnb_id = %s;",
                [already_filled, "BDG00000001"],
            )

        updated = fill_building_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 2)
        rows = read_building_addresses_internal_id()
        self.assertEqual(rows["BDG00000001"], already_filled)

    def test_is_idempotent(self):
        """Running the backfill a second time updates nothing and changes nothing."""
        fill_building_addresses_internal_id(batch_size=2)
        after_first_run = read_building_addresses_internal_id()

        updated = fill_building_addresses_internal_id(batch_size=2)

        self.assertEqual(updated, 0)
        self.assertEqual(read_building_addresses_internal_id(), after_first_run)

    def test_backfill_is_not_historicized(self):
        """Input: buildings backfilled through
        building_versioning_dangerously_disabled().
        Expected: addresses_internal_id is still filled, but no
        batid_building_history row is created and sys_period stays open,
        exactly like a manual write inside that context manager."""
        sys_period_before = Building.objects.get(rnb_id="BDG00000001").sys_period

        fill_building_addresses_internal_id(batch_size=2)

        building = Building.objects.get(rnb_id="BDG00000001")
        self.assertEqual(
            building.addresses_internal_id,
            [
                self.internal_id_by_cle["00000_0000_00001"],
                self.internal_id_by_cle["00000_0000_00002"],
            ],
        )
        self.assertEqual(building.sys_period, sys_period_before)
        self.assertEqual(history_count("BDG00000001"), 0)
        self.assertEqual(history_count("BDG00000002"), 0)

    def test_join_table_is_populated_as_a_side_effect(self):
        """Input: a building backfilled by a raw UPDATE of addresses_internal_id.
        Expected: keep_building_address_link_updated(), which only reacts to
        addresses_internal_id and is untouched by
        building_versioning_dangerously_disabled(), still fires and populates
        BuildingAddressesInternalIdReadOnly."""
        fill_building_addresses_internal_id(batch_size=2)

        internal_ids = set(
            BuildingAddressesInternalIdReadOnly.objects.filter(
                building__rnb_id="BDG00000001"
            ).values_list("address__internal_id", flat=True)
        )
        self.assertEqual(
            internal_ids,
            {
                self.internal_id_by_cle["00000_0000_00001"],
                self.internal_id_by_cle["00000_0000_00002"],
            },
        )


class FillBuildingAddressesInternalIdEmptyTableTestCase(TestCase):
    """Separate from FillBuildingAddressesInternalIdTestCase, which always seeds
    a few buildings in setUp and cannot easily reach an empty table: Building
    rows can never be deleted, even by raw SQL (prevent_building_deletion()
    trigger)."""

    def test_on_empty_table(self):
        """No building at all -> the backfill returns 0 instead of looping."""
        self.assertEqual(fill_building_addresses_internal_id(batch_size=2), 0)
