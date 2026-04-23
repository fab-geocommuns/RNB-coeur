import json

from batid.models import City
from batid.services.administrative_areas import fetch_dpt_cities_geojson
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon


def import_etalab_cities(dpt: str):
    cities_geojson = fetch_dpt_cities_geojson(dpt)

    for c in cities_geojson["features"]:
        geom = GEOSGeometry(json.dumps(c["geometry"]), srid=4326)

        if geom.geom_type == "Polygon":
            # transform into a multipolygon
            geom = MultiPolygon([geom], srid=4326)
        City.objects.update_or_create(
            code_insee=c["properties"]["code"],
            defaults={"shape": geom, "name": c["properties"]["nom"]},
        )
