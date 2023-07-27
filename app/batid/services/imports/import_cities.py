import json

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

from batid.services.france import fetch_dpt_cities_geojson
from batid.models import City


def import_etalab_cities(dpt: str):
    cities_geojson = fetch_dpt_cities_geojson(dpt)

    for c in cities_geojson["features"]:
        geom = GEOSGeometry(json.dumps(c["geometry"]), srid=4326)

        if geom.geom_type == "Polygon":
            # transform into a multipolygon
            geom = MultiPolygon([geom], srid=4326)

        geom.transform(settings.DEFAULT_SRID)

        try:
            city = City.objects.get(code_insee=c["properties"]["code"])
        except City.DoesNotExist:
            city = City(code_insee=c["properties"]["code"])

        city.shape = geom
        city.name = c["properties"]["nom"]
        city.save()
