import json

from django.core.management.base import BaseCommand
import requests
from django.db import connection
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--dpt", type=str, default="")
        parser.add_argument("--city", type=str, default="")

    def handle(self, *args, **options):
        if options["dpt"] == "" and options["city"] == "":
            print("Please provide a departement or a city")
            return

        if options["dpt"] != "" and options["city"] != "":
            print("Please provide a departement or a city, not both")
            return

        if options["dpt"] != "":
            print("Generating export for a departement is not implemented yet")
            return

        if options["city"] != "":
            url = f"https://geo.api.gouv.fr/communes?code={options['city']}&format=geojson&geometry=contour"

            data = requests.get(url).json()

            q = "select rnb_id, ST_AsGeoJSON(shape) as shape from batid_building where ST_Intersects(shape, ST_Transform(%(city_shape)s, %(db_srid)s  )) limit 10"

            c_geom = GEOSGeometry(json.dumps(data["features"][0]["geometry"]))

            with connection.cursor() as cursor:
                fc = {"type": "FeatureCollection", "features": []}

                cursor.execute(
                    q, {"city_shape": f"{c_geom}", "db_srid": settings.DEFAULT_SRID}
                )

                for row in cursor:
                    feature = {
                        "type": "Feature",
                        "properties": {"rnb_id": row[0]},
                        "geometry": json.loads(row[1]),
                    }
                    fc["features"].append(feature)

                # print(len(data))
