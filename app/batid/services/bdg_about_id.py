from batid.models.building import EventType
from batid.utils.db import dictfetchall
from django.db import connection

# Event types linking a deactivated RNB ID to the RNB IDs which replaced it.
# - merge / split: the building(s) created by the event
# - revert_merge / revert_split: the original building(s) reactivated by the revert
LINEAGE_EVENT_TYPES = [
    EventType.MERGE.value,
    EventType.SPLIT.value,
    EventType.REVERT_MERGE.value,
    EventType.REVERT_SPLIT.value,
]


def get_about_id(rnb_id: str) -> dict | None:
    """
    Tell what became of a RNB ID: its current state, the last event it went through
    and, if it is inactive, the active RNB IDs at the end of its lineage.
    Returns None if the RNB ID is unknown.
    """

    q = """
    SELECT
        bdg.rnb_id,
        bdg.is_active,
        bdg.status,
        bdg.event_type,
        lower(bdg.sys_period) AS updated_at,
        json_build_object(
            'type', bdg.event_origin ->> 'source',
            'id',
            case
                when bdg.event_origin ->> 'source' = 'contribution'
                then (bdg.event_origin ->> 'contribution_id')::bigint
                when bdg.event_origin ->> 'source' in ('import', 'data_fix')
                then (bdg.event_origin ->> 'id')::bigint
                else null
            end
        ) AS event_origin,
        case
            when u.id is not null
            then json_build_object(
                'id', u.id,
                'username', u.username,
                'organization_name', author_org.name,
                'organization_short_name', author_org.short_name
            ) else null
        end AS author
    FROM batid_building AS bdg
    LEFT JOIN auth_user AS u ON bdg.event_user_id = u.id
    LEFT JOIN LATERAL (
        SELECT o.name, o.short_name
        FROM batid_userprofile AS up
        JOIN batid_organization AS o ON up.organization_id = o.id
        WHERE up.user_id = u.id
        LIMIT 1
    ) AS author_org ON TRUE
    WHERE bdg.rnb_id = %(rnb_id)s
    """

    with connection.cursor() as cursor:
        rows = dictfetchall(cursor, q, {"rnb_id": rnb_id})

    if not rows:
        return None

    about = rows[0]
    about["active_children"] = get_active_children(rnb_id)

    return about


def get_active_children(rnb_id: str) -> list[str]:
    """
    Follow the lineage of a RNB ID and return the active RNB IDs at the end of it.

    An inactive building is linked to the buildings made active by the event which
    deactivated it (the event_id of its current version):
    - a merge parent leads to the merge child
    - a split parent leads to the split children
    - a reverted merge child leads back to the reactivated merge parents
    - a reverted split child leads back to the reactivated split parent
    Each linked building is then followed in its current state, until active
    buildings (or dead ends, eg a deactivation) are reached.
    """

    q = """
    WITH RECURSIVE lineage AS (
        SELECT bdg.rnb_id, bdg.is_active, bdg.event_id, bdg.event_type
        FROM batid_building AS bdg
        WHERE bdg.rnb_id = %(rnb_id)s

        -- UNION (and not UNION ALL) removes duplicated rows, which stops the recursion
        -- if a building is reached twice
        UNION

        SELECT next_bdg.rnb_id, next_bdg.is_active, next_bdg.event_id, next_bdg.event_type
        FROM lineage AS l
        JOIN batid_building_with_history AS linked
            ON linked.event_id = l.event_id
            AND linked.is_active
            AND linked.rnb_id <> l.rnb_id
        JOIN batid_building AS next_bdg ON next_bdg.rnb_id = linked.rnb_id
        WHERE NOT l.is_active
        AND l.event_type = ANY(%(event_types)s)
    )
    SELECT DISTINCT rnb_id
    FROM lineage
    WHERE is_active AND rnb_id <> %(rnb_id)s
    ORDER BY rnb_id
    """

    params = {"rnb_id": rnb_id, "event_types": LINEAGE_EVENT_TYPES}

    with connection.cursor() as cursor:
        cursor.execute(q, params)
        return [row[0] for row in cursor.fetchall()]
