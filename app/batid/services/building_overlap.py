from typing import Any
from typing import Dict

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection

from batid.exceptions import BuildingOverlapError
from batid.services.bdg_status import BuildingStatus


def check_building_overlap(
    shape: GEOSGeometry,
    exclude_rnb_id: str | None = None,
) -> None:
    """
    Check if a geometry overlaps too much with an existing building.
    Raises BuildingOverlapError if >80% overlap in either direction.

    Args:
        shape: The geometry of the new/modified building
        exclude_rnb_id: Optional rnb_id to exclude from the check (used during updates)

    Raises:
        BuildingOverlapError: If significant overlap is detected
    """
    if shape is None:
        return

    overlapping = _find_overlapping_buildings(shape, exclude_rnb_id)

    if overlapping:
        raise BuildingOverlapError(overlapping)


def _find_overlapping_buildings(
    shape: GEOSGeometry,
    exclude_rnb_id: str | None = None,
) -> list[dict]:
    """
    Find existing buildings that overlap too much with the given geometry.

    Args:
        shape: The geometry to check
        exclude_rnb_id: Optional rnb_id to exclude from the check (used during updates)

    Returns:
        List of dicts {"rnb_id": str, "overlap_ratio": float} for buildings
        exceeding the overlap threshold.
    """

    # SQL query to find intersecting buildings
    # and compute overlap ratios in both directions
    query = """
        WITH new_geom AS (
            SELECT ST_GeomFromText(%(new_shape)s, 4326) as geom
        )
        SELECT
            b.rnb_id,
            CASE
                WHEN ST_Area(ng.geom) > 0 THEN
                    ST_Area(ST_Intersection(b.shape, ng.geom)) / ST_Area(ng.geom)
                ELSE 1
            END as new_in_existing_ratio,
            CASE
                WHEN ST_Area(b.shape) > 0 THEN
                    ST_Area(ST_Intersection(b.shape, ng.geom)) / ST_Area(b.shape)
                ELSE 1
            END as existing_in_new_ratio
        FROM batid_building b, new_geom ng
        WHERE
            b.is_active = true
            AND b.status=ANY(%(real_statuses)s)
            AND ST_Intersects(b.shape, ng.geom)
    """

    params: Dict[str, Any] = {
        "new_shape": shape.wkt,
        "real_statuses": list(BuildingStatus.REAL_BUILDINGS_STATUS),
    }

    if exclude_rnb_id is not None:
        query += "            AND b.rnb_id != %(exclude_rnb_id)s\n"
        params["exclude_rnb_id"] = exclude_rnb_id

    overlapping_buildings = []

    # used in tests to bypass the overlap verification
    BUILDING_OVERLAP_THRESHOLD = settings.BUILDING_OVERLAP_THRESHOLD

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

        for row in rows:
            rnb_id, new_in_existing, existing_in_new = row

            # Take the max ratio from both directions
            max_ratio = max(new_in_existing or 0, existing_in_new or 0)

            if max_ratio > BUILDING_OVERLAP_THRESHOLD:
                overlapping_buildings.append(
                    {
                        "rnb_id": rnb_id,
                        "overlap_ratio": max_ratio,
                    }
                )

    return overlapping_buildings
