from pprint import pprint
from typing import Optional
from django.core.management.base import BaseCommand
import json
from batid.models import Plot
from batid.services.geocoders import (
    GeocodeEarthGeocoder,
    NominatimGeocoder,
    PhotonGeocoder,
)
from batid.services.imports.import_plots import import_etalab_plots
from batid.services.search_bdg import BuildingSearch

from django.contrib.gis.geos import GEOSGeometry, Point

from django.db import connection


class Command(BaseCommand):
    def handle(self, *args, **options):
        with connection.cursor() as cur:
            s = BuildingSearch()

            results = s.get_queryset()

            for b in results:
                print("---------")
                print(b.rnb_id)
                print(b.point_geojson())
