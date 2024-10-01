from django.db import connection

from batid.models import Contribution
from batid.utils.db import dictfetchall
from django.contrib.auth.models import User


def export_format() -> list:

    q = f"SELECT * FROM {Contribution._meta.db_table} ORDER BY created_at DESC"
    with connection.cursor() as cursor:
        return dictfetchall(cursor, q)

def refuse_contributions_on_inactive_bdg(rnb_id: str, user: User):

    msg = f"Ce signalement a été refusé suite à la désactivation du bâtiment {rnb_id}."
    contributions = Contribution.objects.filter(rnb_id=rnb_id, status="pending")

    for c in contributions:
        c.refuse(user, msg)
