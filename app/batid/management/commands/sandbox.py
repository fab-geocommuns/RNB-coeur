import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand

from batid.models import Address, Candidate, Building
from batid.services.candidate import Inspector
from batid.services.imports.import_bdnb7 import (
    import_bdnb7_addresses,
    import_bdnb7_bdgs,
)
from batid.services.imports.import_bdtopo import import_bdtopo
from batid.services.source import Source


class Command(BaseCommand):
    def handle(self, *args, **options):
        Candidate.objects.all().delete()

        import_bdtopo("01")

        Candidate.objects.exclude(source_id="BATIMENT0000000008739051").delete()

        i = Inspector()
        i.inspect()
