import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand

from batid.models import Address, Candidate, Building
from batid.services.candidate import Inspector
from batid.services.imports.import_bdnb7 import (
    import_bdnb7_addresses,
    import_bdnb7_bdgs,
)


class Command(BaseCommand):
    def handle(self, *args, **options):
        geojson = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-1.198300287528582, 48.35550202978007],
                    [-1.198601197941258, 48.355369644278056],
                    [-1.1981612461655686, 48.35516141221896],
                    [-1.1979568346091867, 48.35531310453146],
                    [-1.197899765382573, 48.355505477318815],
                    [-1.198300287528582, 48.35550202978007],
                ]
            ],
        }
        geom = GEOSGeometry(json.dumps(geojson), srid=4326)

        q = f"SELECT id, ST_AsEWKB(point) as point FROM {Building._meta.db_table} LIMIT 10"
        params = {"geom": f"{geom}"}
        params = {}

        qs = Building.objects.raw(q, params)

        print(len(list(qs)))

        for b in qs:
            print(b.id)
            print(b.point)

        # print("-----")
        #
        # q = "SELECT * FROM batid_building LIMIT 10"
        #
        # new_qs = Building.objects.raw(q)
        #
        # print(len(list(new_qs)))
