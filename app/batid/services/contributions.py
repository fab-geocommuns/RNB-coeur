from django.db import connection

from batid.models import Contribution


def export_format() -> list:

    q = f"SELECT * FROM {Contribution._meta.db_table} ORDER BY created_at DESC"
    with connection.cursor() as cursor:
        cursor.execute(q)
        return cursor.fetchall()
