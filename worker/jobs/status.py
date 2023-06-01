from datetime import datetime

from db import get_conn
from psycopg2.extras import execute_values


def add_default_status() -> int:
    count = 0

    # query all buildings without status
    select_q = (
        "SELECT b.id "
        "FROM batid_building b "
        "LEFT JOIN batid_buildingstatus as s ON b.id = s.building_id "
        "WHERE s.id IS NULL "
        "LIMIT 100000"
    )

    insert_q = (
        "INSERT INTO batid_buildingstatus (building_id, type, created_at, is_current) "
        "VALUES %s"
    )

    conn = get_conn()
    with conn.cursor() as cursor:
        cursor.execute(select_q)
        rows = cursor.fetchall()

        values = [(row[0], "constructed", datetime.now(), True) for row in rows]
        count += len(values)

        execute_values(cursor, insert_q, values, page_size=1000)
        conn.commit()

    return count
