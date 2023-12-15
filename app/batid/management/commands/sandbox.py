import csv

import fiona
from django.core.management.base import BaseCommand

from batid.models import Building, Candidate
from batid.services.candidate import Inspector
from batid.services.source import Source
from batid.services.imports.import_bdtopo import import_bdtopo
from batid.tasks import dl_source


class Command(BaseCommand):
    def handle(self, *args, **options):
        Candidate.objects.all().delete()

        import_bdtopo("bdtopo_2023_09", "972")
