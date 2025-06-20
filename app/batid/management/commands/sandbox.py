import time
from django.core.management.base import BaseCommand

from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        start = time.perf_counter()
        c = fill_empty_event_id(5000)
        end = time.perf_counter()
        duration = end - start
        print(f"Time taken: {duration:.2f} seconds")
        print(f"Updated {c} rows with empty event_id")

        duration_per_row = duration / c if c > 0 else 0
        objective = 40_000_000
        estimated_seconds = (objective / c) * duration if c > 0 else float("inf")
        estimated_hours = estimated_seconds / 3600
        estimated_days = estimated_hours / 24
        print(
            f"Estimated time to complete {objective} rows: {estimated_hours:.2f} hours ({estimated_days:.2f} days)"
        )
