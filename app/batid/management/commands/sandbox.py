from batid.services.source import Source
from django.core.management.base import BaseCommand
import pandas as pd
from batid.services.imports.import_dgfip_ads import import_dgfip_ads_achievements


class Command(BaseCommand):
    def handle(self, *args, **options):
        import_dgfip_ads_achievements("ads-dgfip-dummy.csv")
