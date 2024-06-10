import json

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon

from batid.models import City
from batid.services.administrative_areas import fetch_dpt_cities_geojson


def import_etalab_cities(dpt: str):
    cities_geojson = fetch_dpt_cities_geojson(dpt)

    for c in cities_geojson["features"]:
        geom = GEOSGeometry(json.dumps(c["geometry"]), srid=4326)

        if geom.geom_type == "Polygon":
            # transform into a multipolygon
            geom = MultiPolygon([geom], srid=4326)
        try:
            city = City.objects.get(code_insee=c["properties"]["code"])
        except City.DoesNotExist:
            city = City(code_insee=c["properties"]["code"])

        city.shape = geom
        city.name = c["properties"]["nom"]
        city.save()
