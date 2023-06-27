from time import perf_counter

from batid.models import BuildingStatus
from django.core.management.base import BaseCommand

from batid.services.building import add_default_status


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("-- remove")
        BuildingStatus.objects.all().delete()

        print("-- create")
        start = perf_counter()
        add_default_status()
        end = perf_counter()
        print(f"-- done in {end - start:0.4f} seconds")
