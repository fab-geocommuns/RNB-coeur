from contextlib import contextmanager

from django.db import connection
from django.db.transaction import TransactionManagementError
from django.utils import timezone
from psycopg2.extras import DateTimeTZRange


def dictfetchall(cursor, query, params=None):
    cursor.execute(query, params)
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def dictfetchone(cursor, query, params=None):
    cursor.execute(query, params)
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, cursor.fetchone()))


def list_to_pgarray(alist):
    return "{" + ",".join(alist) + "}"


def from_now_to_infinity():
    now = timezone.now()
    return DateTimeTZRange(now, None)


# Session setting read by the building_versioning_trigger WHEN clause
# (see migration 0146). When truthy, the trigger does not fire.
DISABLE_BUILDING_VERSIONING_SETTING = "rnb.disable_building_versioning"


@contextmanager
def building_versioning_dangerously_disabled():
    """
    !!WARNING!!
    Use with caution if you have a good reason to do it. Most probably a database
    migration/backfill on the building table.

    Skip the historisation of the building table for the current transaction.

    Inside this context manager, writes on batid_building do not create rows in
    batid_building_history and do not update the sys_period column. Only the
    current transaction is affected: concurrent sessions keep historicizing
    their own writes, and the building table is never locked (unlike
    "ALTER TABLE ... DISABLE TRIGGER", which is global and takes an exclusive
    lock).

    Must be used inside a transaction: SET LOCAL has no effect in autocommit
    mode, which would silently keep the historisation on.

    You can also skip the historisation using raw SQL in a transaction.
    ```sql
    begin;
    SET LOCAL rnb.disable_building_versioning = 'on';

    UPDATE batid_building SET ... WHERE ...;
    ...

    commit;
    ```
    """

    if not connection.in_atomic_block:
        raise TransactionManagementError(
            "building_versioning_dangerously_disabled() must be used inside a transaction, "
            "otherwise the building history would still be written."
        )

    with connection.cursor() as cursor:
        # remember the current value, so that nesting two context managers
        # does not turn the versioning back on when the inner one exits
        cursor.execute(
            "SELECT current_setting(%s, true)", [DISABLE_BUILDING_VERSIONING_SETTING]
        )
        previous_value = cursor.fetchone()[0] or "off"
        cursor.execute(f"SET LOCAL {DISABLE_BUILDING_VERSIONING_SETTING} = 'on'")

    try:
        yield
    finally:
        # Leaving the transaction resets the setting on its own. We only restore
        # it here for the rest of a still healthy transaction; on a broken one,
        # any query would fail anyway.
        if not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SET LOCAL {DISABLE_BUILDING_VERSIONING_SETTING} = %s",
                    [previous_value],
                )
