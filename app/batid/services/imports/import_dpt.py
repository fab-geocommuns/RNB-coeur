import json

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.db import connection

from batid.models import Department, Department_subdivided

from batid.services.administrative_areas import fetch_dpt_cities_geojson


def import_etalab_dpts() -> None:

    for dpt in dpts:
        cities = fetch_dpt_cities_geojson(dpt["code"])

        if not cities["features"]:
            print(f"No cities found for {dpt['code']}")
            continue

        polys = []

        for city in cities["features"]:
            if city["geometry"]["type"] == "Polygon":
                polys.append(city["geometry"])
            elif city["geometry"]["type"] == "MultiPolygon":
                for poly in city["geometry"]["coordinates"]:
                    polys.append({"type": "Polygon", "coordinates": poly})

        geoms = [GEOSGeometry(json.dumps(p), srid=4326) for p in polys]

        mp = MultiPolygon(geoms, srid=4326)
        try:
            dpt_model = Department.objects.get(code=dpt["code"])
        except Department.DoesNotExist:
            dpt_model = Department(code=dpt["code"])

        dpt_model.name = dpt["nom"]
        dpt_model.shape = mp
        dpt_model.save()

        # Also build the sub-divided version
        Department_subdivided.objects.filter(code=dpt["code"]).delete()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO batid_department_subdivided (code, name, shape)
                SELECT code, name, ST_SubDivide(shape) as shape
                FROM batid_department;
                """
            )


def import_one_department(code: str):
    pass
