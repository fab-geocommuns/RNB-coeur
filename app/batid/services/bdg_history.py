from django.db.models.query import QuerySet
from django.db import connection

from batid.utils.db import dictfetchall


def get_history_rows(rnb_id: str = None, event_id: str = None) -> QuerySet:

    q = """
    SELECT 
    bdg.rnb_id, 
    bdg.is_active,
    ST_AsGeoJSON(bdg.shape)::json AS shape,
    bdg.status,
    bdg.ext_ids::json,
    lower(bdg.sys_period) AS updated_at,
    (
        SELECT COALESCE(json_agg(
            json_build_object(
                'id', adr.id,
                'source', adr.source,
                'street_number', adr.street_number,
                'street_rep', adr.street_rep,
                'street', adr.street,
                'city_name', adr.city_name,
                'city_zipcode', adr.city_zipcode,
                'city_insee_code', adr.city_insee_code
            ) 
        ), '[]'::json)
        FROM public.batid_address AS adr 
        WHERE adr.id = ANY(bdg.addresses_id) 
    ) as addresses 
    FROM batid_building_with_history as bdg
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
