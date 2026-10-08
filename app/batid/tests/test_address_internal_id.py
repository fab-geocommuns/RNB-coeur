from batid.models import Address
from django.db import IntegrityError, connection, transaction
from django.test import TestCase


def read_internal_ids() -> dict:
    """Read internal_id straight from the database, keyed by interop key."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT cle_interop, internal_id FROM batid_address;")
        return dict(cursor.fetchall())


class AddressInternalIdDefaultTestCase(TestCase):
    """The column DEFAULT must apply on every write path, Django ones included."""

    def test_orm_create(self):
        """Address.objects.create (used by save_new_address) -> internal_id is set."""
        Address.objects.create(cle_interop="01001_0001_00001", source="ban")

        internal_ids = read_internal_ids()

        self.assertIsNotNone(internal_ids["01001_0001_00001"])

    def test_bulk_create(self):
        """bulk_create(ignore_conflicts=True), as used by the BAN import -> internal_id is set."""
        Address.objects.bulk_create(
            [
                Address(cle_interop="01001_0001_00001", source="ban"),
                Address(cle_interop="01001_0001_00002", source="ban"),
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
                INSERT INTO batid_address (cle_interop, source, created_at, updated_at)
                VALUES ('01001_0001_00001', 'bdnb', now(), now());
                """)

        internal_ids = read_internal_ids()

        self.assertIsNotNone(internal_ids["01001_0001_00001"])

    def test_values_are_distinct(self):
        """Two addresses created in a row get two different internal_ids."""
        Address.objects.create(cle_interop="01001_0001_00001", source="ban")
        Address.objects.create(cle_interop="01001_0001_00002", source="ban")

        internal_ids = read_internal_ids()

        self.assertNotEqual(
            internal_ids["01001_0001_00001"], internal_ids["01001_0001_00002"]
        )

    def test_created_instance_carries_its_internal_id(self):
        """Address.objects.create -> the instance returned holds the internal_id the
        database drew, which is also its primary key."""
        address = Address.objects.create(cle_interop="01001_0001_00001", source="ban")

        self.assertEqual(address.internal_id, read_internal_ids()["01001_0001_00001"])
        self.assertEqual(address.pk, address.internal_id)


class AddressPrimaryKeyTestCase(TestCase):
    """internal_id is the primary key of batid_address, cle_interop a plain unique
    column."""

    def setUp(self):
        Address.objects.create(cle_interop="01001_0001_00001", source="ban")
        Address.objects.create(cle_interop="01001_0001_00002", source="ban")

    def test_internal_id_is_the_primary_key(self):
        """
        Input: the primary key of the Django model and of the table.
        Expected: internal_id alone, on both sides.
        """
        self.assertEqual(Address._meta.pk.name, "internal_id")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                    ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'batid_address'::regclass AND i.indisprimary;
                """)
            primary_key_columns = [row[0] for row in cursor.fetchall()]

        self.assertEqual(primary_key_columns, ["internal_id"])

    def test_cle_interop_is_unique(self):
        """
        Input: a second address created with the interop key of an existing one.
        Expected: IntegrityError, now raised by the UNIQUE constraint on
        cle_interop rather than by the primary key.
        """
        with self.assertRaises(IntegrityError), transaction.atomic():
            Address.objects.create(cle_interop="01001_0001_00001", source="ban")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'batid_address'::regclass AND c.contype = 'u'
                    AND a.attname = 'cle_interop';
                """)
            self.assertEqual(cursor.fetchall(), [("cle_interop",)])

    def test_join_table_references_the_primary_key(self):
        """
        Input: the foreign key of the building <> address join table.
        Expected: it targets batid_address.internal_id, now the primary key.
        """
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                    ON a.attrelid = c.confrelid AND a.attnum = ANY(c.confkey)
                WHERE c.contype = 'f'
                    AND c.conrelid = 'batid_buildingaddressesinternalidreadonly'::regclass
                    AND c.confrelid = 'batid_address'::regclass;
                """)
            self.assertEqual(cursor.fetchall(), [("internal_id",)])

    def test_duplicate_internal_id_is_rejected(self):
        """An address forced onto the internal_id of another one -> IntegrityError."""
        internal_ids = read_internal_ids()

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE batid_address SET internal_id = %s WHERE cle_interop = %s;",
                    [internal_ids["01001_0001_00001"], "01001_0001_00002"],
                )

    def test_null_internal_id_is_rejected(self):
        """An address whose internal_id is emptied -> IntegrityError."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE batid_address SET internal_id = NULL WHERE cle_interop = %s;",
                    ["01001_0001_00001"],
                )
