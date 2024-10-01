from django.db import connection

from batid.models import Contribution
from batid.utils.db import dictfetchall
from django.contrib.auth.models import User


def export_format() -> list:

    q = f"SELECT * FROM {Contribution._meta.db_table} ORDER BY created_at DESC"
    with connection.cursor() as cursor:
        return dictfetchall(cursor, q)




