from venv import logger

from django.db import connection
from django.db import transaction


def fill_building_random_id():
    keep_going = True
    empty_lines_count = 0
    filled_lines_count = 0

    with connection.cursor() as cursor:
        count_empty_random_id_sql = """
            SELECT count(*)
            FROM batid_building
            WHERE random_id IS NULL;
        """
        cursor.execute(count_empty_random_id_sql)
        fetchone = cursor.fetchone()
        if fetchone:
            empty_lines_count = fetchone[0]
        logger.info(f"Number of empty random_id: {empty_lines_count}")

    while keep_going:
        with connection.cursor() as cursor:
            with transaction.atomic():
                disable_trigger_sql = "ALTER TABLE public.batid_building DISABLE TRIGGER building_versioning_trigger;"
                cursor.execute(disable_trigger_sql)

                fill_random_id_sql = """
                    UPDATE batid_building b
                    SET random_id = ('x' || encode(gen_random_bytes(8), 'hex'))::bit(64)::bigint
                    WHERE ctid IN (
                    SELECT ctid
                    FROM batid_building
                    WHERE random_id IS NULL
                    LIMIT 5
                    );
                """
                cursor.execute(fill_random_id_sql)

                # Check if we have to continue the loop
                keep_going = cursor.rowcount > 0

                filled_lines_count += cursor.rowcount
                logger.info(
                    f"Number of filled random_id: {filled_lines_count} / {empty_lines_count}"
                )

                enable_trigger_sql = "ALTER TABLE public.batid_building ENABLE TRIGGER building_versioning_trigger;"
                cursor.execute(enable_trigger_sql)

    return f"Updated {filled_lines_count} rows"
