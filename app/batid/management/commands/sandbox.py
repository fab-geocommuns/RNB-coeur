from pprint import pprint
from typing import Optional
from django.core.management.base import BaseCommand
import json
from batid.models import Plot, Building
from batid.services.geocoders import (
    GeocodeEarthGeocoder,
    NominatimGeocoder,
    PhotonGeocoder,
)
from batid.services.imports.import_plots import import_etalab_plots
from batid.services.list_bdg import public_bdg_queryset
from batid.services.search_bdg import BuildingSearch

from django.contrib.gis.geos import GEOSGeometry, Point

from django.db import connection


class Command(BaseCommand):
    def handle(self, *args, **options):
        results = public_bdg_queryset()[:10]

        print(results.query)

        # results = Building.objects.all()[:10]
        for b in results:
            print(b.rnb_id)
