import csv

import fiona
from django.core.management.base import BaseCommand
from batid.services.source import Source
from batid.services.imports.import_bdtopo import import_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **options):
        import_bdtopo("bdtopo_2023_09", "38")
