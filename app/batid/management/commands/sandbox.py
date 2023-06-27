from time import perf_counter

from batid.services.search_bdg import BuildingSearch
from batid.services.source import Source
from django.core.management.base import BaseCommand
import pandas as pd
from batid.services.imports.import_dgfip_ads import import_dgfip_ads_achievements


class Command(BaseCommand):
    def handle(self, *args, **options):
        loops = 1
        duration = 0
        for _ in range(loops):
            s = BuildingSearch()
            s.set_params(
                bb="44.85286264607754,-0.5931455176501856,44.85092733766149,-0.5826084823448241"
            )
            start = perf_counter()
            qs = s.get_queryset()
            c = qs.count()
            end = perf_counter()

            duration += end - start

        print(f"Average : {duration/loops:.3f}s per search")
