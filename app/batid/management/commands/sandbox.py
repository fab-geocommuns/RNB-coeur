import json

from django.contrib.gis.geos import Point, GEOSGeometry
from django.core.management.base import BaseCommand
from batid.list_bdg import list_bdgs
from batid.services.building import add_default_status
from batid.services.guess_bdg import BuildingGuess
from batid.services.vector_tiles import url_params_to_tile, tile_sql
from batid.tests.test_inspector import get_bdtopo_data


class Command(BaseCommand):
    def handle(self, *args, **options):
        rows = get_bdtopo_data()

        for row in rows:
            print("--")
            print(row["id"])

            mp = GEOSGeometry(json.dumps(row["geometry"]))
            mp.srid = 2154

            mp = mp.transform(4326, clone=True)

            print(mp.json)
