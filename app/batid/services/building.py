import json
import os
from datetime import datetime, timezone
from time import perf_counter
from batid.services.france import fetch_city_geojson
from batid.services.source import Source, BufferToCopy
from batid.models import Building, BuildingStatus, Department
from django.db import connection
from psycopg2.extras import RealDictCursor
from django.conf import settings


def remove_dpt_bdgs(dpt_code: str):
    print(f"remove bdgs from department {dpt_code}")

    dpt = Department.objects.get(code=dpt_code)
    Building.objects.filter(point__intersects=dpt.shape).delete()


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
        "SELECT rnb_id, ext_bdtopo_id, ST_AsGeoJSON(ST_Transform(shape, 4326)) as shape "
        f"FROM {Building._meta.db_table} "
        "WHERE ST_Intersects(shape, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(db_srid)s)) "
    )

    with connection.cursor() as cursor:
        params = {
            "geom": json.dumps(cities_geojson["features"][0]["geometry"]),
            "db_srid": 4326,
        }
        cursor.execute(q, params)

        # export the result to a geojson featurecollection
        # with rnb_id and bdtopo_id as properties

        feature_collection = {"type": "FeatureCollection", "features": []}

        for rnb_id, bdtopo_id, shape in cursor:
            feature = {
                "type": "Feature",
                "properties": {
                    "rnb_id": rnb_id,
                    "bdtopod_id": bdtopo_id,
                },
                "geometry": json.loads(shape),
            }
            feature_collection["features"].append(feature)

        with open(src.path, "w") as f:
            json.dump(feature_collection, f)


def add_default_status(after_id=0) -> int:
    count = 0

    last_id = None

    # query all buildings without status
    select_q = (
        "SELECT b.id "
        f"FROM {Building._meta.db_table} b "
        "LEFT JOIN batid_buildingstatus as s ON b.id = s.building_id "
        "WHERE s.id IS NULL and b.id > %(after_id)s "
        "ORDER BY b.id ASC "
        "LIMIT 300000"
    )

    buffer = BufferToCopy()

    with connection.cursor() as cursor:
        start = perf_counter()
        cursor.execute(select_q, {"after_id": after_id})
        rows = cursor.fetchall()
        end = perf_counter()
        print(f"fetch done in {end - start:0.4f} seconds. Found {len(rows)} rows")

        values = [
            (row[0], "constructed", datetime.now(), datetime.now(), True)
            for row in rows
        ]

        if values:
            print("-- writing buffer")
            buffer.write_data(values)
            count += len(values)

            start = perf_counter()
            with open(buffer.path, "r") as f:
                print("-- copy buffer to db")
                cursor.copy_from(
                    f,
                    BuildingStatus._meta.db_table,
                    sep=";",
                    columns=(
                        "building_id",
                        "type",
                        "created_at",
                        "updated_at",
                        "is_current",
                    ),
                )
            end = perf_counter()
            print(f"insert done in {end - start:0.4f} seconds)")

            os.remove(buffer.path)

            last_id = rows[-1][0]

    return count, last_id
