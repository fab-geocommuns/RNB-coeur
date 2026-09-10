from contextlib import contextmanager

from batid.models import Building, BuildingHistoryOnly
from batid.utils.db import building_versioning_disabled
from django.db import connection, connections, transaction
from django.db.transaction import TransactionManagementError
from django.db.utils import DatabaseError, InternalError
from django.test import TestCase, TransactionTestCase


@contextmanager
def other_db_session():
    """
    Open a second, independent connection to the test database, to observe what
    a concurrent session sees and can do.
    """
    other_connection = connections.create_connection("default")
    try:
        # do not let a lock conflict hang the test suite: if the building table
        # were locked by the session under test, we want a clean failure
        with other_connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '10s'")
        yield other_connection
    finally:
        other_connection.close()


def history_count(rnb_id):
    return BuildingHistoryOnly.objects.filter(rnb_id=rnb_id).count()


class DisableBuildingVersioningTestCase(TestCase):
    """Effect of building_versioning_disabled() on the versioning trigger."""

    def test_update_is_not_historicized(self):
        """
        Input: a building updated with save() inside
        building_versioning_disabled().
        Expected: the new value is written, no history row is created and the
        building stays the current version (open sys_period).
        """
        building = Building.objects.create(rnb_id="VERSION0001")

        with building_versioning_disabled():
            building.parent_buildings = [1]
            building.save()

        building.refresh_from_db()
        self.assertEqual(building.parent_buildings, [1])
        self.assertEqual(history_count("VERSION0001"), 0)
        self.assertIsNone(building.sys_period.upper)

    def test_sys_period_is_left_untouched(self):
        """
        Input: a building updated inside building_versioning_disabled() with a
        query that does not write the sys_period column.
        Expected: the sys_period keeps the exact value it had before the
        update, since the trigger no longer maintains it.
        """
        Building.objects.create(rnb_id="VERSION0008")
        sys_period_before = Building.objects.get(rnb_id="VERSION0008").sys_period

        with building_versioning_disabled():
            Building.objects.filter(rnb_id="VERSION0008").update(parent_buildings=[1])

        building = Building.objects.get(rnb_id="VERSION0008")
        self.assertEqual(building.parent_buildings, [1])
        self.assertEqual(building.sys_period, sys_period_before)
        self.assertEqual(history_count("VERSION0008"), 0)

    def test_insert_is_not_historicized(self):
        """
        Input: a building created inside building_versioning_disabled().
        Expected: the row is created with an open sys_period (from the Django
        default, since the trigger did not set it) and no history row.
        """
        with building_versioning_disabled():
            building = Building.objects.create(rnb_id="VERSION0002")

        building.refresh_from_db()
        self.assertIsNotNone(building.sys_period.lower)
        self.assertIsNone(building.sys_period.upper)
        self.assertEqual(history_count("VERSION0002"), 0)

    def test_several_updates_are_not_historicized(self):
        """
        Input: three successive updates of the same building inside the context
        manager.
        Expected: none of them is historicized, only the last value is kept.
        """
        building = Building.objects.create(rnb_id="VERSION0003")

        with building_versioning_disabled():
            for i in range(3):
                building.parent_buildings = [i]
                building.save()

        building.refresh_from_db()
        self.assertEqual(building.parent_buildings, [2])
        self.assertEqual(history_count("VERSION0003"), 0)

    def test_versioning_resumes_after_the_context_manager(self):
        """
        Input: an update inside the context manager, then another one after it,
        in the same transaction.
        Expected: only the update made after the context manager is
        historicized.
        """
        building = Building.objects.create(rnb_id="VERSION0004")

        with building_versioning_disabled():
            building.parent_buildings = [1]
            building.save()

        self.assertEqual(history_count("VERSION0004"), 0)

        building.parent_buildings = [2]
        building.save()

        self.assertEqual(history_count("VERSION0004"), 1)
        # the history row holds the value written while versioning was off
        history_row = BuildingHistoryOnly.objects.get(rnb_id="VERSION0004")
        self.assertEqual(history_row.parent_buildings, [1])

    def test_versioning_resumes_after_an_exception(self):
        """
        Input: an exception raised inside the context manager and caught
        outside of it, then a new update.
        Expected: the setting is restored, so the new update is historicized.
        """
        building = Building.objects.create(rnb_id="VERSION0005")

        with self.assertRaises(ValueError):
            with building_versioning_disabled():
                building.parent_buildings = [1]
                building.save()
                raise ValueError("something went wrong")

        building.parent_buildings = [2]
        building.save()

        self.assertEqual(history_count("VERSION0005"), 1)

    def test_nested_context_managers(self):
        """
        Input: two nested building_versioning_disabled(), with an update after
        the inner one is closed but still inside the outer one.
        Expected: the inner context manager does not turn the versioning back
        on, so nothing is historicized before the outer one is closed.
        """
        building = Building.objects.create(rnb_id="VERSION0009")

        with building_versioning_disabled():
            with building_versioning_disabled():
                building.parent_buildings = [1]
                building.save()

            building.parent_buildings = [2]
            building.save()

        self.assertEqual(history_count("VERSION0009"), 0)

        building.parent_buildings = [3]
        building.save()

        self.assertEqual(history_count("VERSION0009"), 1)

    def test_other_building_triggers_are_still_active(self):
        """
        Input: a raw SQL DELETE on a building inside the context manager.
        Expected: only the versioning trigger is skipped, the trigger
        forbidding building deletions still fires.
        """
        Building.objects.create(rnb_id="VERSION0006")

        with building_versioning_disabled():
            with self.assertRaises(InternalError):
                # the failing statement is isolated in a savepoint, so that the
                # surrounding transaction stays usable
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "delete from batid_building where rnb_id = 'VERSION0006';"
                        )

        self.assertEqual(Building.objects.filter(rnb_id="VERSION0006").count(), 1)

    def test_an_invalid_setting_value_is_rejected(self):
        """
        Input: the session setting set by hand to a value that is not a boolean.
        Expected: writing a building fails, rather than silently skipping (or
        performing) the historisation.
        """
        Building.objects.create(rnb_id="VERSION0007")

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET LOCAL rnb.disable_building_versioning = 'not a boolean'"
                    )
                Building.objects.filter(rnb_id="VERSION0007").update(
                    parent_buildings=[1]
                )


class ConcurrentBuildingVersioningTestCase(TransactionTestCase):
    """
    Disabling the versioning must be strictly local to one transaction: other
    sessions keep historicizing their writes and are never blocked.
    """

    def setUp(self):
        Building.objects.create(rnb_id="CONCURRENT01")
        Building.objects.create(rnb_id="CONCURRENT02")

    def test_other_session_still_historicizes_and_is_not_blocked(self):
        """
        Input: session A updates a building with the versioning disabled, and
        while its transaction is still open, session B updates another
        building.
        Expected: session B is not blocked, its own update is historicized, and
        session A's update is not.
        """
        with transaction.atomic():
            with building_versioning_disabled():
                Building.objects.filter(rnb_id="CONCURRENT01").update(
                    parent_buildings=[1]
                )

                with other_db_session() as other_connection:
                    with other_connection.cursor() as cursor:
                        cursor.execute(
                            "update batid_building set parent_buildings = '[2]' "
                            "where rnb_id = 'CONCURRENT02';"
                        )
                        cursor.execute(
                            "select count(*) from batid_building_history "
                            "where rnb_id = 'CONCURRENT02';"
                        )
                        self.assertEqual(cursor.fetchone()[0], 1)

        self.assertEqual(history_count("CONCURRENT01"), 0)
        self.assertEqual(history_count("CONCURRENT02"), 1)

    def test_the_building_table_is_not_locked(self):
        """
        Input: session A writes a building with the versioning disabled.
        Expected: seen from another session, session A only holds the ordinary
        row-level write lock on the building table, and none of the table-wide
        locks that "ALTER TABLE ... DISABLE TRIGGER" would take.
        """
        blocking_locks = [
            "ShareLock",
            "ShareRowExclusiveLock",
            "ExclusiveLock",
            "AccessExclusiveLock",
        ]

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("select pg_backend_pid();")
                session_pid = cursor.fetchone()[0]

            with building_versioning_disabled():
                Building.objects.filter(rnb_id="CONCURRENT01").update(
                    parent_buildings=[1]
                )

                with other_db_session() as other_connection:
                    with other_connection.cursor() as cursor:
                        cursor.execute(
                            "select mode from pg_locks "
                            "where relation = 'batid_building'::regclass "
                            "and pid = %s;",
                            [session_pid],
                        )
                        modes = [row[0] for row in cursor.fetchall()]

        self.assertIn("RowExclusiveLock", modes)
        for mode in blocking_locks:
            self.assertNotIn(mode, modes)

    def test_the_setting_does_not_leak_out_of_the_transaction(self):
        """
        Input: a transaction using the context manager, then a new transaction
        on the same connection.
        Expected: the setting is reset by the end of the transaction, so the
        next write is historicized again.
        """
        with transaction.atomic():
            with building_versioning_disabled():
                Building.objects.filter(rnb_id="CONCURRENT01").update(
                    parent_buildings=[1]
                )

        Building.objects.filter(rnb_id="CONCURRENT01").update(parent_buildings=[2])

        self.assertEqual(history_count("CONCURRENT01"), 1)

    def test_outside_of_a_transaction_is_forbidden(self):
        """
        Input: the context manager used in autocommit mode, outside of any
        transaction.
        Expected: it raises TransactionManagementError instead of silently
        keeping the versioning on, because SET LOCAL would have no effect.
        """
        self.assertFalse(connection.in_atomic_block)

        with self.assertRaises(TransactionManagementError):
            with building_versioning_disabled():
                pass  # pragma: no cover

        Building.objects.filter(rnb_id="CONCURRENT01").update(parent_buildings=[1])
        self.assertEqual(history_count("CONCURRENT01"), 1)
