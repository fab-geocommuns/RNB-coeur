import json

from batid.models import Department
from batid.services.france import fetch_dpt_cities_geojson, fetch_departments_refs
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.conf import settings


def import_etalab_dpts() -> None:
    dpts = fetch_departments_refs()

    for dpt in dpts:
        cities = fetch_dpt_cities_geojson(dpt["code"])

        polys = []

        for city in cities["features"]:
            if city["geometry"]["type"] == "Polygon":
                polys.append(city["geometry"])
            elif city["geometry"]["type"] == "MultiPolygon":
                for poly in city["geometry"]["coordinates"]:
                    polys.append({"type": "Polygon", "coordinates": poly})

        geoms = [GEOSGeometry(json.dumps(p), srid=4326) for p in polys]

        mp = MultiPolygon(geoms, srid=4326)
        mp = mp.transform(settings.DEFAULT_SRID, clone=True)

        try:
            dpt_model = Department.objects.get(code=dpt["code"])
        except Department.DoesNotExist:
            dpt_model = Department(code=dpt["code"])

        dpt_model.name = dpt["nom"]
        dpt_model.shape = mp
        dpt_model.save()
