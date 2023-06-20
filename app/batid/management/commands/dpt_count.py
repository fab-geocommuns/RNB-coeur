import json
from concurrent.futures import ThreadPoolExecutor
from django.core.management.base import BaseCommand

from django.conf import settings
from django.db import connection

from batid.services.city import dpt_codes, fetch_dpt_cities_geojson
from batid.models import Building
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon



class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--dpt", type=str, default="all")


    def handle(self, *args, **options):

        codes = dpt_codes() if options["dpt"] == "all" else options["dpt"].split(",")

        # multithread dpt handling

        with ThreadPoolExecutor() as executor:
            results = executor.map(_dpt_contour, codes)

            dpts = []
            for result in results:
                dpts.append(result)

        dpts = sorted(dpts, key=lambda d: d["code"])

        q = "SELECT COUNT(id) FROM batid_building WHERE ST_Intersects(point, ST_Envelope(%(dpt_shape)s))"


        # Count building in each dpt
        with connection.cursor() as cursor:
            for dpt in dpts:
                # count = Building.objects.filter(point__intersects=dpt['shape']).count()

                cursor.execute(q, {"dpt_shape": f"{dpt['shape']}"})

                count = cursor.fetchone()[0]
                print(f"{dpt['code']} - {count}")





def _dpt_contour(code: str) -> dict:

    cities = fetch_dpt_cities_geojson(code)

    polys = []

    for city in cities["features"]:

        if city["geometry"]["type"] == "Polygon":
            polys.append(city["geometry"])
        elif city["geometry"]["type"] == "MultiPolygon":

            for poly in city["geometry"]["coordinates"]:
                polys.append({
                    "type": "Polygon",
                    "coordinates": poly
                })

    geoms = [GEOSGeometry(json.dumps(p), srid=4326) for p in polys]

    mp = MultiPolygon(geoms, srid=4326)
    mp = mp.transform(settings.DEFAULT_SRID, clone=True)



    return {
        "code": code,
        "shape": mp
    }









