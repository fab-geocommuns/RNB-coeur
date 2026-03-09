import json

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.db import connection

from batid.models import Department
from batid.models import Department_subdivided
from batid.services.administrative_areas import dpt_name
from batid.services.administrative_areas import dpts_list
from batid.services.administrative_areas import fetch_dpt_cities_geojson
from batid.services.administrative_areas import validate_dpt_code


def import_etalab_dpts() -> None:

    dpts = dpts_list()

    for dpt in dpts:
        import_one_department(dpt)


def import_one_department(code: str):

    if not validate_dpt_code(code):
        raise ValueError(f"Invalid department code: {code}")

    # First, we get all the cities for this department
    # Those cities have the polygons we want to import
    cities = fetch_dpt_cities_geojson(code)

    if not cities["features"]:
        print(f"No cities found for {code}")
        return

    polys = []

    for city in cities["features"]:
        if city["geometry"]["type"] == "Polygon":
            polys.append(city["geometry"])
        elif city["geometry"]["type"] == "MultiPolygon":
            for poly in city["geometry"]["coordinates"]:
                polys.append({"type": "Polygon", "coordinates": poly})

    geoms = [GEOSGeometry(json.dumps(p), srid=4326) for p in polys]
    mp = MultiPolygon(geoms, srid=4326)

    # Then we upsert the department
    try:
        dpt_model = Department.objects.get(code=code)
    except Department.DoesNotExist:
        dpt_model = Department(code=code)

    dpt_model.name = dpt_name(code)
    dpt_model.shape = mp
    dpt_model.save()

    # Finally, we build the sub-divided version
    # It is used for faster queries (eg: in data.gouv.fr dataset export)
    Department_subdivided.objects.filter(code=code).delete()

    with connection.cursor() as cursor:
        cursor.execute(f"""
            INSERT INTO {Department_subdivided._meta.db_table} (code, name, shape)
            SELECT code, name, ST_SubDivide(shape) as shape
            FROM {Department._meta.db_table};
            """)
