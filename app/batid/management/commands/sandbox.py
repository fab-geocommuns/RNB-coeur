from pprint import pprint
from typing import Optional
from django.core.management.base import BaseCommand
import json
from batid.models import Plot
from batid.services.geocoders import GeocodeEarthGeocoder, NominatimGeocoder, PhotonGeocoder
from batid.services.imports.import_plots import import_etalab_plots
from batid.services.search_bdg import BuildingSearch

from django.contrib.gis.geos import GEOSGeometry, Point

class Command(BaseCommand):

    


    def handle(self, *args, **options):

        g = NominatimGeocoder()
        r = g.geocode({"q": "notre dame de paris"})

        pprint(r)

        
