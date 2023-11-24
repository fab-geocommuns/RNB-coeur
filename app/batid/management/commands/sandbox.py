import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from batid.list_bdg import list_bdgs
from batid.services.building import add_default_status
from batid.services.guess_bdg import BuildingGuess
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_bdgs
from batid.services.source import Source
from batid.tasks import dl_source

from batid.models import Candidate, Building, BuildingStatus
from batid.services.bdg_status import BuildingStatus as BuildingStatusService


class Command(BaseCommand):
    def handle(self, *args, **options):
        # dl_source("bdnb_2023_01", "75")

        import_bdnd_2023_01_bdgs("75")
        pass
