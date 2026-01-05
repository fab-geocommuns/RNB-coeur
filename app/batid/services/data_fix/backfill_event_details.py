import logging

from django.db import connection
from django.db import transaction

from batid.models import Building


def _ensure_history_queue_table():
    """
    Creates and populates the queue table for historical records if it doesn't exist or is empty.
    """
    with connection.cursor() as cursor:
        # Set statement timeout to 1 hour
        cursor.execute("SET statement_timeout = '1h';")

        # Create the queue table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS batid_eventdetail_backfill_history_queue (
                id SERIAL PRIMARY KEY,
                event_id UUID NOT NULL,
                rnb_id VARCHAR(12) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_backfill_history_queue_event_id
                ON batid_eventdetail_backfill_history_queue(event_id);
        """
        )

        # Check if the table is empty
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM batid_eventdetail_backfill_history_queue LIMIT 1);"
        )
        table_has_rows = cursor.fetchone()[0]

        # If empty, populate it with event_ids that need backfilling
        if not table_has_rows:
            cursor.execute(
                """
                INSERT INTO batid_eventdetail_backfill_history_queue (event_id, rnb_id)
                SELECT DISTINCT b.event_id, b.rnb_id
                FROM batid_building_history b
                WHERE b.event_id IS NOT NULL
                  AND b.event_type IS NOT NULL
                  AND b.event_origin IS NOT NULL
                  AND b.point IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM batid_eventdetail ed
                      WHERE ed.event_id = b.event_id
                  )
                ORDER BY b.event_id;
            """
            )
            cursor.execute(
                "SELECT COUNT(*) FROM batid_eventdetail_backfill_history_queue;"
            )
            count = cursor.fetchone()[0]


def _ensure_current_queue_table():
    """
    Creates and populates the queue table for current records if it doesn't exist or is empty.
    """
    with connection.cursor() as cursor:
        # Set statement timeout to 1 hour
        cursor.execute("SET statement_timeout = '1h';")

        # Create the queue table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS batid_eventdetail_backfill_current_queue (
                id SERIAL PRIMARY KEY,
                event_id UUID NOT NULL,
                rnb_id VARCHAR(12) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_backfill_current_queue_event_id
                ON batid_eventdetail_backfill_current_queue(event_id);
        """
        )

        # Check if the table is empty
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM batid_eventdetail_backfill_current_queue LIMIT 1);"
        )
        table_has_rows = cursor.fetchone()[0]

        # If empty, populate it with event_ids that need backfilling
        if not table_has_rows:
            cursor.execute(
                """
                INSERT INTO batid_eventdetail_backfill_current_queue (event_id, rnb_id)
                SELECT DISTINCT b.event_id, b.rnb_id
                FROM batid_building b
                WHERE b.event_id IS NOT NULL
                  AND b.event_type IS NOT NULL
                  AND b.event_origin IS NOT NULL
                  AND b.point IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM batid_eventdetail ed
                      WHERE ed.event_id = b.event_id
                  )
                ORDER BY b.event_id;
            """
            )
            cursor.execute(
                "SELECT COUNT(*) FROM batid_eventdetail_backfill_current_queue;"
            )
            count = cursor.fetchone()[0]


def backfill_event_details_history(batch_size: int = 1000) -> int:
    """
    Backfills EventDetail and BuildingEventDetail for historical building records.

    This function pops event_ids from a queue table and processes them in batches.
    The queue table is created and populated on first run.

    Args:
        batch_size: Number of historical records to process in one batch

    Returns:
        Number of historical records processed
    """

    # Ensure queue table exists and is populated
    _ensure_history_queue_table()

    with transaction.atomic():
        with connection.cursor() as cursor:
            # Set statement timeout to 1 hour
            cursor.execute("SET statement_timeout = '1h';")

            # Step 1: Pop items from the queue
            dequeue_sql = """
                DELETE FROM batid_eventdetail_backfill_history_queue
                WHERE id IN (
                    SELECT id
                    FROM batid_eventdetail_backfill_history_queue
                    ORDER BY id
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING event_id, rnb_id;
            """

            cursor.execute(dequeue_sql, [batch_size])
            queue_items = cursor.fetchall()

            print(f"Dequeued {len(queue_items)} items from history queue")

            if not queue_items:
                return 0

            # Step 2: Process each item
            processed_count = 0
            for idx, (event_id, rnb_id) in enumerate(queue_items, 1):
                print(f"Processing history building {idx}/{len(queue_items)}: {rnb_id} (event: {event_id})")

                process_sql = """
                    SELECT insert_or_update_event_detail_from_history_row(b.*)
                    FROM batid_building_history b
                    WHERE b.event_id = %s AND b.rnb_id = %s;
                """

                cursor.execute(process_sql, [event_id, rnb_id])
                processed_count += 1

            return processed_count


def backfill_event_details_current(batch_size: int = 1000) -> int:
    """
    Backfills EventDetail and BuildingEventDetail for current building records.

    This function pops event_ids from a queue table and processes them in batches.
    The queue table is created and populated on first run.

    Args:
        batch_size: Number of current records to process in one batch

    Returns:
        Number of current records processed
    """

    # Ensure queue table exists and is populated
    _ensure_current_queue_table()

    with transaction.atomic():
        with connection.cursor() as cursor:
            # Set statement timeout to 1 hour
            cursor.execute("SET statement_timeout = '1h';")

            # Step 1: Pop items from the queue
            dequeue_sql = """
                DELETE FROM batid_eventdetail_backfill_current_queue
                WHERE id IN (
                    SELECT id
                    FROM batid_eventdetail_backfill_current_queue
                    ORDER BY id
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING event_id, rnb_id;
            """

            cursor.execute(dequeue_sql, [batch_size])
            queue_items = cursor.fetchall()

            print(f"Dequeued {len(queue_items)} items from current queue")

            if not queue_items:
                return 0

            # Step 2: Process each item
            processed_count = 0
            for idx, (event_id, rnb_id) in enumerate(queue_items, 1):
                print(f"Processing current building {idx}/{len(queue_items)}: {rnb_id} (event: {event_id})")

                process_sql = """
                    SELECT insert_or_update_event_detail(b)
                    FROM batid_building b
                    WHERE b.event_id = %s AND b.rnb_id = %s;
                """

                cursor.execute(process_sql, [event_id, rnb_id])
                processed_count += 1

            return processed_count
