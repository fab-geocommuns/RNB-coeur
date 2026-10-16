from datetime import datetime, timedelta

from batid.models import EditionActivity
from django.db import connection
from django.db.models import Max
from django.utils import timezone

# sys_period starts at the transaction start time (CURRENT_TIMESTAMP), so an edition
# can become visible after more recent ones have been processed. Each incremental run
# re-scans this window; already processed events are skipped thanks to the unique event_id.
RESCAN_WINDOW = timedelta(hours=1)

# One row per contribution event. When an event touches several buildings (merge, split),
# the point of an active building (the merged one, a split child) is preferred.
INSERT_EDITION_ACTIVITY_SQL = """
    WITH events AS (
        SELECT DISTINCT ON (bdg.event_id)
            bdg.event_id,
            bdg.event_type,
            bdg.event_user_id,
            lower(bdg.sys_period) AS edited_at,
            bdg.point
        FROM batid_building_with_history bdg
        WHERE lower(bdg.sys_period) >= %(since)s
          AND lower(bdg.sys_period) < %(until)s
          AND bdg.event_origin ->> 'source' = 'contribution'
          AND bdg.event_user_id IS NOT NULL
        ORDER BY bdg.event_id, bdg.is_active DESC, bdg.point IS NULL
    )
    INSERT INTO batid_editionactivity (
        event_id, event_type, user_id, organization_id, city_id, department_id,
        edited_at, created_at
    )
    SELECT
        e.event_id,
        e.event_type,
        e.event_user_id,
        up.organization_id,
        (
            SELECT c.id FROM batid_city c
            WHERE ST_Intersects(c.shape, e.point)
            LIMIT 1
        ),
        (
            SELECT d.id FROM batid_department d
            WHERE d.code = (
                SELECT ds.code FROM batid_department_subdivided ds
                WHERE ST_Intersects(ds.shape, e.point)
                LIMIT 1
            )
        ),
        e.edited_at,
        now()
    FROM events e
    LEFT JOIN batid_userprofile up ON up.user_id = e.event_user_id
    ON CONFLICT (event_id) DO NOTHING
"""


def record_edition_activity(since: datetime, until: datetime) -> int:
    """
    Insert one EditionActivity row per contribution event whose edition time
    is in [since, until). Events already recorded are ignored.
    Returns the number of inserted rows.
    """
    with connection.cursor() as cursor:
        cursor.execute(INSERT_EDITION_ACTIVITY_SQL, {"since": since, "until": until})
        return cursor.rowcount


def record_recent_edition_activity() -> int:
    """
    Incremental run: record the editions made since the last recorded one
    (minus RESCAN_WINDOW). On an empty table, only the last RESCAN_WINDOW is scanned:
    older editions are expected to be loaded with the backfill_edition_activity command.
    Returns the number of inserted rows.
    """
    now = timezone.now()
    last_edited_at = EditionActivity.objects.aggregate(last=Max("edited_at"))["last"]
    since = (last_edited_at or now) - RESCAN_WINDOW
    return record_edition_activity(since, now)
