import uuid

from django.db import transaction
from batid.models import BuildingHistoryOnly


def _fetch_history_rows(batch_size=10_000):

    # Django select for update
    return BuildingHistoryOnly.objects.select_for_update(skip_locked=True).filter(
        event_id=None, event_type__in=[None, "creation", "update"]
    )[:batch_size]


def fill_empty_event_id():

    # Do past versions first
    with transaction.atomic():
        while True:
            rows = _fetch_history_rows()
            for row in rows:
                row.event_id = uuid.uuid4()
                row.save()
