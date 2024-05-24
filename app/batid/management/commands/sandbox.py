import json
from pprint import pprint

import geopandas as gpd
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from shapely.geometry import mapping

from batid.services.guess_bdg_new import Guesser
from batid.services.guess_bdg_new import PartialRoofHandler


class Command(BaseCommand):
    def handle(self, *args, **options):

        pass
