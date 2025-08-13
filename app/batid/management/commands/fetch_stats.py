from django.core.management.base import BaseCommand

from batid.services.stats import compute_stats  # type: ignore[import-not-found]
from batid.services.stats import get_path


class Command(BaseCommand):
    def handle(self, *args, **options):

        print("Fetching stats...")
        compute_stats()
        print("Done.")
        print(f"Stats have been saved in {get_path()}")
