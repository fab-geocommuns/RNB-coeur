import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand

from batid.models import Candidate, Building, BuildingStatus
from batid.services.bdg_status import BuildingStatus as BuildingStatusService


class Command(BaseCommand):
    def handle(self, *args, **options):
        pass
