from django.db import connection


def dictfetchall(cursor, query, params=None):

    cursor.execute(query, params)
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]