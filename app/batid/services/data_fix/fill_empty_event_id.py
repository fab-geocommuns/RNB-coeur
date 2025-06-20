import uuid

from django.db import connection
from django.db import transaction

from batid.models import Building
from batid.models import BuildingHistoryOnly


def _fetch_old_rows(batch_size: int):

    # Django select for update
    return BuildingHistoryOnly.objects.select_for_update(skip_locked=True).filter(
        event_id=None, event_type__in=["creation", "update"]
    )[:batch_size]


def _fetch_current_rows(batch_size: int):

    # Django select for update
    return Building.objects.select_for_update(skip_locked=True).filter(
        event_id=None, event_type__in=["creation", "update"]
    )[:batch_size]


def fill_empty_event_id(batch_size: int = 50_000) -> int:

    updated_rows = 0

    # Do past versions first
    with transaction.atomic():

        old_rows = _fetch_old_rows(batch_size)

        if old_rows:

            # Assign a new UUID to each ro
            for row in old_rows:
                row.event_id = uuid.uuid4()

            # Save in bulk to avoid multiple queries
            updated_rows += BuildingHistoryOnly.objects.bulk_update(
                old_rows, ["event_id"]
            )

    # Do current versions next
    with transaction.atomic():
        with connection.cursor() as cursor:

            remaining_batch_size = batch_size - updated_rows

            current_rows = _fetch_current_rows(remaining_batch_size)

            if current_rows:

                disable_trigger_sql = "ALTER TABLE public.batid_building DISABLE TRIGGER building_versioning_trigger;"
                cursor.execute(disable_trigger_sql)

                # Assign a new UUID to each row
                for row in current_rows:
                    row.event_id = uuid.uuid4()

                # Save in bulk to avoid multiple queries
                updated_rows += Building.objects.bulk_update(current_rows, ["event_id"])

                enable_trigger_sql = "ALTER TABLE public.batid_building ENABLE TRIGGER building_versioning_trigger;"
                cursor.execute(enable_trigger_sql)

    return updated_rows
