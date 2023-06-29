import requests
from django.db import connection

from batid.models import Department
from batid.utils.db import dictfetchone


def fetch_city_geojson(insee_code: int) -> dict:
    url = f"https://geo.api.gouv.fr/communes?code={insee_code}&format=geojson&geometry=contour"
    return requests.get(url).json()


def fetch_dpt_cities_geojson(dpt: str) -> dict:
    url = f"https://geo.api.gouv.fr/departements/{dpt}/communes?format=geojson&geometry=contour"
    return requests.get(url).json()


def fetch_departments_refs() -> dict:
    url = "https://geo.api.gouv.fr/departements"
    return requests.get(url).json()


def dpt_codes() -> set:
    metro = {str(i).zfill(2) for i in range(1, 96)}
    metro.add("2A")
    metro.add("2B")
    metro.remove("20")
    outre_mer = set(["971", "972", "973", "974", "976"])
    return metro.union(outre_mer)


# Returns a dict representation of the WGS84 bbox of the metropolitan area
def get_metropolitan_bbox() -> dict:
    # We use ht departments since this is the smallest table.
    # Works with buildings would be too "expensive".
    # Idea : instead of calculating, it could be stored in a file/variable somewhere
    q = (
        "SELECT ST_XMin(sub.bbox) as x_min, "
        "ST_XMax(sub.bbox) as x_max, "
        "ST_YMin(sub.bbox) as y_min, "
        "ST_YMax(sub.bbox) as y_max "
        "FROM ("
        f"select ST_Extent(ST_Transform(shape, 4326)) as bbox from {Department._meta.db_table} "
        f") sub"
    )

    with connection.cursor() as cursor:
        return dictfetchone(cursor, q)
