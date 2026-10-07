from django.db import connection
from django.test import TestCase


class TestAddressesIdDropped(TestCase):
    """addresses_id (BAN interop keys) is gone: addresses_internal_id is the only
    building <> address link, and nothing in the database refers to the old one."""

    def test_addresses_id_is_not_a_column_anymore(self):
        """
        Input: the columns of batid_building, batid_building_history and of the
        batid_building_with_history view (a "SELECT *" frozen at its creation).
        Expected: none of them has addresses_id, all of them have
        addresses_internal_id (the view was recreated after the drop).
        """
        for relation in (
            "batid_building",
            "batid_building_history",
            "batid_building_with_history",
        ):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s",
                    [relation],
                )
                columns = {row[0] for row in cursor.fetchall()}

            self.assertNotIn("addresses_id", columns, relation)
            self.assertIn("addresses_internal_id", columns, relation)

    def test_old_join_table_is_gone(self):
        """
        Input: the building <> address join tables.
        Expected: batid_buildingaddressesreadonly does not exist anymore,
        batid_buildingaddressesinternalidreadonly does.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('batid_buildingaddressesreadonly'), "
                "to_regclass('batid_buildingaddressesinternalidreadonly')"
            )
            old_table, new_table = cursor.fetchone()

        self.assertIsNone(old_table)
        self.assertIsNotNone(new_table)

    def test_trigger_functions_do_not_refer_to_addresses_id(self):
        """
        Input: the source of the two trigger functions that used to read
        addresses_id, keep_building_address_link_updated() and
        check_address_is_linked().
        Expected: neither mentions addresses_id nor the old join table. PL/pgSQL
        does not check column names when a function is created, so a leftover
        would only fail at the first write on batid_building.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proname, prosrc FROM pg_proc "
                "WHERE proname IN ('keep_building_address_link_updated', "
                "'check_address_is_linked')"
            )
            functions = dict(cursor.fetchall())

        self.assertEqual(len(functions), 2)
        for name, source in functions.items():
            self.assertNotIn("addresses_id", source, name)
            self.assertNotIn("buildingaddressesreadonly", source, name)
