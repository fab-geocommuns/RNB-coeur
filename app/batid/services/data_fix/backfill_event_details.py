from django.db import connection
from django.db import transaction

from batid.models import Building


def backfill_event_details(batch_size: int = 1000) -> int:
    with transaction.atomic():
        with connection.cursor() as cursor:
            # Fetch buildings that have the required fields but don't have EventDetail yet
            # We use raw SQL to call the PostgreSQL function efficiently
            sql = """
                WITH buildings_to_process AS (
                    SELECT b.*
                    FROM batid_building b
                    WHERE b.event_id IS NOT NULL
                      AND b.event_type IS NOT NULL
                      AND b.event_origin IS NOT NULL
                      AND b.point IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM batid_eventdetail ed
                          WHERE ed.event_id = b.event_id
                      )
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                SELECT
                    insert_or_update_event_detail(b.*),
                    b.rnb_id
                FROM buildings_to_process b;
            """

            cursor.execute(sql, [batch_size])
            results = cursor.fetchall()

            return len(results)
