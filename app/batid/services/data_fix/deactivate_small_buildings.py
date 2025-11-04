from django.conf import settings
from django.db import connection
from django.contrib.auth.models import User
from batid.models.others import DataFix
from batid.models.building import Building


def deactivate_small_buildings(fix_id: int, limit: int = 1000) -> int:

    deactivated_count = 0

    # Try to get the datafix. Will raise DoesNotExist if not found
    data_fix = DataFix.objects.get(id=fix_id)

    # Check the user is set
    if not isinstance(data_fix.user, User):
        raise Exception("DataFix user is not set")

    q = """
        SELECT id FROM batid_building
        WHERE is_active
        AND ST_AREA(shape, true) < %(min_area)s
        AND ST_GeometryType(shape) != 'ST_Point'
        LIMIT %(limit)s
        """

    with connection.cursor() as cursor:
        while True:

            # Get the building ids to deactivate
            params = {"min_area": settings.MIN_BUILDING_AREA, "limit": limit}
            cursor.execute(q, params)
            rows = cursor.fetchall()

            if not rows:
                break

            ids = [row[0] for row in rows]

            for id in ids:
                building = Building.objects.get(id=id)
                building.deactivate()
                deactivated_count += 1

    return deactivated_count
