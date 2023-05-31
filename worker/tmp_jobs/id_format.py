from db import get_conn
from psycopg2.extras import execute_values


def change_id_format() -> int:
    # select all rows which have rnb_id of length 17
    select_q = (
        "SELECT id, rnb_id "
        "FROM batid_building "
        "WHERE length(rnb_id) = 17 LIMIT 100000"
    )

    update_q = "UPDATE batid_building SET rnb_id = v.new_rnb_id FROM (VALUES %s) as v(id, new_rnb_id) WHERE batid_building.id = v.id"

    conn = get_conn()
    params = []
    count = 0
    with conn.cursor() as cursor:
        cursor.execute(select_q)
        for id, rnb_id in cursor:
            count += 1
            # split string in 3 parts, based on a "-" separator
            parts = rnb_id.split("-")
            # keep the 4 first letters of each part
            parts = [part[:4] for part in parts]
            # join parts with nothing
            new_rnb_id = "".join(parts)

            print(f"{rnb_id} -> {new_rnb_id}")

            params.append((id, new_rnb_id))

    with conn.cursor() as cursor:
        execute_values(cursor, update_q, params, page_size=1000)
        conn.commit()

    return count
