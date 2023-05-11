import json

import requests
from db import get_conn
from settings import settings
import psycopg2


def remove_dpt(dpt: str):
    print(f"remove_dpt {dpt}")
    url = f"https://geo.api.gouv.fr/departements/{dpt}/communes?format=geojson&geometry=contour"
    cities_geojson = requests.get(url).json()

    q = (
        "DELETE "
        "FROM batid_building "
        "WHERE ST_Intersects(shape, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(db_srid)s)) "
    )

    conn = get_conn()
    with conn.cursor() as cursor:
        for c in cities_geojson["features"]:
            name = c["properties"]["nom"]

            print(f"Removing bdgs in {name} (insee : {c['properties']['code']})")

            params = {
                "geom": json.dumps(c["geometry"]),
                "db_srid": settings["DEFAULT_SRID"],
            }

            try:
                cursor.execute(q, params)
                conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                conn.rollback()
                cursor.close()
                raise error
