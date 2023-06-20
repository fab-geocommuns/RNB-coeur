import json
from datetime import datetime, timezone

import requests
from batid.services.city import fetch_dpt_cities_geojson, fetch_city_geojson
from batid.services.source import Source
from batid.models import Building, City, BuildingStatus
from django.db import connection
from psycopg2.extras import RealDictCursor, execute_values
from django.conf import settings



def remove_dpt(dpt: str):
    print(f"remove_dpt {dpt}")

    cities_geojson = fetch_dpt_cities_geojson(dpt)

    q = (
        "DELETE "
        f"FROM {Building._meta.db_table} "
        "WHERE ST_Intersects(shape, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(db_srid)s)) "
    )

    with connection.cursor() as cursor:
        for c in cities_geojson["features"]:
            name = c["properties"]["nom"]

            print(f"Removing bdgs in {name} (insee : {c['properties']['code']})")

            params = {
                "geom": json.dumps(c["geometry"]),
                "db_srid": settings.DEFAULT_SRID,
            }

            try:
                cursor.execute(q, params)
                connection.commit()
            except Exception as error:
                connection.rollback()
                cursor.close()
                raise error


def remove_light_bdgs(dpt):
    dpt = dpt.zfill(3)

    src = Source("bdtopo")
    src.set_param("dpt", dpt)

    print(f"########## REMOVE LIGHT BDGS in DPT {dpt} ##########")

    q = (
        f"SELECT id FROM {Building._meta.db_table} WHERE "
        "ST_DWithin(shape, ST_GeomFromText(%(light_shape)s, %(db_srid)s), 0) AND "
        "ST_Equals(shape, ST_GeomFromText(%(light_shape)s, %(db_srid)s))"
    )

    ids = []
    c = 0
    r_count = 0
    with fiona.open(src.find(src.filename)) as f:
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            for feature in f:
                c += 1
                # print(c)

                if feature["properties"]["LEGER"] == "Oui":
                    mp = feature_to_multipoly(feature)
                    cur.execute(q, {"light_shape": mp.wkt, "db_srid": settings.SRID})

                    for bdg in cur:
                        r_count += 1
                        ids.append(bdg["id"])

                    if len(ids) % 5000 == 0:
                        _remove(ids, conn)
                        ids = []

            _remove(ids, connection)

    print(f"########## TOTAL REMOVED: {r_count}")


def _remove(ids, conn):
    if len(ids) > 0:
        print(f"##############################")
        print(f"Remove {len(ids)}")
        del_q = f"DELETE FROM {Building._meta.db_table} WHERE id in %(ids)s"
        params = {"ids": tuple(ids)}
        with conn.cursor() as cur:
            cur.execute(del_q, params)
            conn.commit()


def export_city(insee_code: str):
    src = Source("export")
    src.set_param("city", insee_code)
    src.set_param("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    cities_geojson = fetch_city_geojson(insee_code)

    q = (
        "SELECT rnb_id, ST_AsGeoJSON(shape) as shape "
        f"FROM {Building._meta.db_table} "
        "WHERE ST_Intersects(shape, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(db_srid)s)) "
    )

    with connection.cursor() as cursor:
        params = {
            "geom": json.dumps(cities_geojson["features"][0]["geometry"]),
            "db_srid": settings.DEFAULT_SRID,
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


def add_default_status() -> int:
    count = 0

    # query all buildings without status
    select_q = (
        "SELECT b.id "
        f"FROM {Building._meta.db_table} b "
        "LEFT JOIN batid_buildingstatus as s ON b.id = s.building_id "
        "WHERE s.id IS NULL "
        "LIMIT 100000"
    )

    insert_q = (
        f"INSERT INTO {BuildingStatus._meta.db_table}  (building_id, type, created_at, updated_at, is_current) "
        "VALUES %s"
    )

    with connection.cursor() as cursor:
        cursor.execute(select_q)
        rows = cursor.fetchall()

        values = [
            (row[0], "constructed", datetime.now(), datetime.now(), True)
            for row in rows
        ]
        count += len(values)

        execute_values(cursor, insert_q, values, page_size=1000)
        connection.commit()

    return count
