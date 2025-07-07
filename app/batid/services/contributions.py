from django.db import connection
from psycopg2 import sql

from batid.models import Contribution
from batid.utils.db import dictfetchall


def export_format() -> list:

    q = sql.SQL("SELECT * FROM {contribution} ORDER BY created_at DESC").format(
        contribution=sql.Identifier(Contribution._meta.db_table),
    )
    with connection.cursor() as cursor:
        return dictfetchall(cursor, q)
