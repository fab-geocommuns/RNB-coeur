from psycopg2.extras import DateTimeTZRange
from django.utils import timezone


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
