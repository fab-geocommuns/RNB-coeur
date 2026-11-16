import time
from datetime import timedelta

from batid.utils.db import long_query_timeout
from django.db.models import Min
from django.utils import timezone
from rest_framework_tracking.models import APIRequestLog

# No API request log is kept longer than one year.
RETENTION = timedelta(days=365)
BATCH_SIZE = 10_000
# No new batch after one hour: a large backlog spreads over several nights
# instead of holding a worker slot until morning.
TIME_BUDGET_SECONDS = 3600


def delete_expired_api_request_logs() -> int:
    """
    Delete the API request logs older than RETENTION, by batches of consecutive ids,
    from the smallest id up to the newest expired row. Returns the number of rows deleted.
    """
    # Started before the first queries: they count in the budget.
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    cutoff = timezone.now() - RETENTION
    # Reads the requested_at index (a few pages). Not aggregate(Max("id")) with
    # this filter: the planner walks the primary key backwards through every kept row.
    with long_query_timeout():
        boundary = (
            APIRequestLog.objects.filter(requested_at__lt=cutoff)
            .order_by("-requested_at")
            .values_list("id", flat=True)
            .first()
        )
        if boundary is None:
            return 0
        low = APIRequestLog.objects.aggregate(Min("id"))["id__min"]

    deleted = 0
    while low <= boundary and time.monotonic() < deadline:
        # Id ranges, not pk__in on rows ordered by date: no per-row primary key
        # lookup, and the dead rows of previous batches are never read again.
        # The requested_at filter guarantees no recent row is deleted, whatever
        # the id order; a late expired row is caught the next night.
        # One short transaction per batch, under the long timeout: deleting the
        # large bodies of old rows can exceed the worker statement timeout.
        with long_query_timeout():
            count, _ = APIRequestLog.objects.filter(
                id__gte=low, id__lt=low + BATCH_SIZE, requested_at__lt=cutoff
            ).delete()
        deleted += count
        low += BATCH_SIZE
    return deleted
