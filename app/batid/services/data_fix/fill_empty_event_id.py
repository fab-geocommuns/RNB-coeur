import uuid

from django.db import transaction
from batid.models import BuildingHistoryOnly


def _fetch_old_rows(batch_size=10_000):

    # Django select for update
    return BuildingHistoryOnly.objects.select_for_update(skip_locked=True).filter(
        event_id=None, event_type__in=["creation", "update"]
    )[:batch_size]


def fill_empty_event_id() -> bool:

    updated_some_rows = False

    # Do past versions first
    with transaction.atomic():

        old_rows = _fetch_old_rows()

        if old_rows:

            # Assign a new UUID to each ro
            for row in old_rows:
                row.event_id = uuid.uuid4()

            # Save in bulk to avoid multiple queries
            BuildingHistoryOnly.objects.bulk_update(old_rows, ["event_id"])

            updated_some_rows = True

    return updated_some_rows
