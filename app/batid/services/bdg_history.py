from django.db.models.query import QuerySet
from django.db import connection

from batid.utils.db import dictfetchall

from batid.models import BuildingWithHistory


def get_history_rows(rnb_id: str = None, event_id: str = None) -> QuerySet:

    q = """
    SELECT 
    rnb_id, 
    ST_AsGeoJSON(shape)::json AS shape,
    status,
    ext_ids::json as ext_ids,
    updated_at
    FROM batid_building_with_history
    WHERE 1=1
    """
    params = {}
    # if rnb_id:
    #     q += " AND rnb_id = %(rnb_id)s"
    #     params["rnb_id"] = rnb_id
    # elif event_id:
    #     q += " AND event_id = %(event_id)s"
    #     params["event_id"] = event_id

    q += " ORDER BY lower(sys_period) DESC LIMIT 1"

    params = {}

    with connection.cursor() as cursor:
        return dictfetchall(cursor, q, params)
