import csv

import fiona
from django.core.management.base import BaseCommand
from batid.services.source import Source
from batid.services.imports.import_bdtopo import import_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **options):
        # import_bdtopo("38")

        src = Source("bdtopo")
        src.set_param("dpt", "972")

        # with fiona.open(src.find(src.filename)) as f:
        #     pass

        print(src.find(src.filename))
