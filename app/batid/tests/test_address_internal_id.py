from batid.models import Address
from batid.services.data_fix.fill_address_internal_id import fill_address_internal_id
from django.db import IntegrityError, connection, transaction
from django.test import TestCase


def read_internal_ids() -> dict:
    """Read internal_id straight from the database, keyed by interop key."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, internal_id FROM batid_address;")
        return dict(cursor.fetchall())


def clear_internal_ids(*address_ids: str) -> None:
    """Bring the given addresses back to the state they had before migration 0146.

    internal_id is NOT NULL since migration 0147, so the constraint has to be
    lifted to reproduce that state. The test case runs inside a transaction, so
    this DDL is rolled back along with the rows it allows.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE batid_address ALTER COLUMN internal_id DROP NOT NULL;"
        )
        cursor.execute(
            "UPDATE batid_address SET internal_id = NULL WHERE id = ANY(%s);",
            [list(address_ids)],
        )


class AddressInternalIdDefaultTestCase(TestCase):
    """The column DEFAULT must apply on every write path, Django ones included."""

    def test_orm_create(self):
        """Address.objects.create (used by save_new_address) -> internal_id is set."""
        Address.objects.create(id="01001_0001_00001", source="ban")

        internal_ids = read_internal_ids()

        self.assertIsNotNone(internal_ids["01001_0001_00001"])

    def test_bulk_create(self):
        """bulk_create(ignore_conflicts=True), as used by the BAN import -> internal_id is set."""
        Address.objects.bulk_create(
            [
                Address(id="01001_0001_00001", source="ban"),
                Address(id="01001_0001_00002", source="ban"),
            ],
            ignore_conflicts=True,
        )

        internal_ids = read_internal_ids()

        self.assertIsNotNone(internal_ids["01001_0001_00001"])
        self.assertIsNotNone(internal_ids["01001_0001_00002"])

    def test_raw_insert_with_explicit_columns(self):
        """Raw INSERT listing its columns, as used by the BDNB import -> internal_id is set."""
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO batid_address (id, source, created_at, updated_at)
                VALUES ('01001_0001_00001', 'bdnb', now(), now());
                """)

        internal_ids = read_internal_ids()

        self.assertIsNotNone(internal_ids["01001_0001_00001"])

    def test_values_are_distinct(self):
        """Two addresses created in a row get two different internal_ids."""
        Address.objects.create(id="01001_0001_00001", source="ban")
        Address.objects.create(id="01001_0001_00002", source="ban")

        internal_ids = read_internal_ids()

        self.assertNotEqual(
            internal_ids["01001_0001_00001"], internal_ids["01001_0001_00002"]
        )


class FillAddressInternalIdTestCase(TestCase):
    """Backfill of the addresses that predate the column."""

    def setUp(self):
        # Five addresses spread over two interop key prefixes, so that a batch
        # size of 2 produces several batches and a non trivial ordering.
        self.address_ids = [
            "01001_0001_00001",
            "01001_0001_00002",
            "01001_0001_00003",
            "02002_0002_00001",
            "02002_0002_00002",
        ]
        for address_id in self.address_ids:
            Address.objects.create(id=address_id, source="ban")

    def test_fills_every_empty_row(self):
        """All five addresses emptied -> all five filled, with distinct values."""
        clear_internal_ids(*self.address_ids)

        updated = fill_address_internal_id(batch_size=2)

        self.assertEqual(updated, 5)
        internal_ids = read_internal_ids()
        self.assertEqual(len(internal_ids), 5)
        self.assertNotIn(None, internal_ids.values())
        self.assertEqual(len(set(internal_ids.values())), 5)

    def test_does_not_overwrite_existing_values(self):
        """Only two addresses emptied -> the three others keep their exact value."""
        untouched_before = read_internal_ids()
        clear_internal_ids("01001_0001_00002", "02002_0002_00001")

        updated = fill_address_internal_id(batch_size=2)

        self.assertEqual(updated, 2)
        internal_ids = read_internal_ids()
        for address_id in ["01001_0001_00001", "01001_0001_00003", "02002_0002_00002"]:
            self.assertEqual(internal_ids[address_id], untouched_before[address_id])

    def test_is_idempotent(self):
        """Running the backfill a second time updates nothing and changes nothing."""
        clear_internal_ids(*self.address_ids)
        fill_address_internal_id(batch_size=2)
        after_first_run = read_internal_ids()

        updated = fill_address_internal_id(batch_size=2)

        self.assertEqual(updated, 0)
        self.assertEqual(read_internal_ids(), after_first_run)

    def test_on_empty_table(self):
        """No address at all -> the backfill returns 0 instead of looping."""
        Address.objects.all().delete()

        self.assertEqual(fill_address_internal_id(batch_size=2), 0)


class AddressInternalIdConstraintsTestCase(TestCase):
    """The unique index and the NOT NULL constraint installed by migration 0147."""

    def setUp(self):
        Address.objects.create(id="01001_0001_00001", source="ban")
        Address.objects.create(id="01001_0001_00002", source="ban")

    def test_duplicate_internal_id_is_rejected(self):
        """An address forced onto the internal_id of another one -> IntegrityError."""
        internal_ids = read_internal_ids()

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE batid_address SET internal_id = %s WHERE id = %s;",
                    [internal_ids["01001_0001_00001"], "01001_0001_00002"],
                )

    def test_null_internal_id_is_rejected(self):
        """An address whose internal_id is emptied -> IntegrityError."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE batid_address SET internal_id = NULL WHERE id = %s;",
                    ["01001_0001_00001"],
                )
