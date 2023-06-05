import json

from db import get_conn
from services.source import Source
from datetime import datetime, timezone
import requests
from settings import settings


def export_city(insee_code: str):
    src = Source("export")
    src.set_param("city", insee_code)
    src.set_param("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    cities_geojson = get_city_geojson(insee_code)

    q = (
        "SELECT rnb_id, ST_AsGeoJSON(shape) as shape "
        "FROM batid_building "
        "WHERE ST_Intersects(shape, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(db_srid)s)) "
    )

    conn = get_conn()
    with conn.cursor() as cursor:
        params = {
            "geom": json.dumps(cities_geojson["features"][0]["geometry"]),
            "db_srid": settings["DEFAULT_SRID"],
        }
        cursor.execute(q, params)

        # export the result to a geojson featurecollection
        # with a property rnb_id
        # and a property source

        feature_collection = {"type": "FeatureCollection", "features": []}

        for rnb_id, shape in cursor:
            feature = {
                "type": "Feature",
                "properties": {
                    "rnb_id": rnb_id,
                },
                "geometry": json.loads(shape),
            }
            feature_collection["features"].append(feature)

        with open(src.path, "w") as f:
            json.dump(feature_collection, f)


def get_city_geojson(insee_code: int) -> dict:
    url = f"https://geo.api.gouv.fr/communes?code={insee_code}&format=geojson&geometry=contour"
    return requests.get(url).json()
