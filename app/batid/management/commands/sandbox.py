import time
from django.core.management.base import BaseCommand

from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        start = time.perf_counter()
        c = fill_empty_event_id(1000)
        end = time.perf_counter()
        print(f"Time taken: {end - start:.2f} seconds")
        print(f"Updated {c} rows with empty event_id")

        pass
