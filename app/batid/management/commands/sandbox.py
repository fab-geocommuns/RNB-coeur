from time import perf_counter

from batid.models import Candidate, Building
from django.core.management.base import BaseCommand

from batid.services.building import add_default_status
from batid.services.candidate import Inspector


class Command(BaseCommand):
    def handle(self, *args, **options):
        # print("-- remove")
        # Building.objects.all().delete()

        print("-- create")
        start = perf_counter()

        i = Inspector()
        i.inspect()

        end = perf_counter()
        print(f"-- done in {end - start:0.4f} seconds")
