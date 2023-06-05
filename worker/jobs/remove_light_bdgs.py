from jobs.import_bdtopo import feature_to_multipoly
from shapely.geometry import mapping, shape, MultiPolygon
from psycopg2.extras import RealDictCursor, execute_values
from services.source import Source
import fiona
from db import get_conn
from settings import settings


def remove_light_bdgs(dpt):
    dpt = dpt.zfill(3)

    src = Source("bdtopo")
    src.set_param("dpt", dpt)

    print(f"########## REMOVE LIGHT BDGS in DPT {dpt} ##########")

    q = (
        "SELECT id FROM batid_building WHERE "
        "ST_DWithin(shape, ST_GeomFromText(%(light_shape)s, %(db_srid)s), 0) AND "
        "ST_Equals(shape, ST_GeomFromText(%(light_shape)s, %(db_srid)s))"
    )
    conn = get_conn()

    ids = []
    c = 0
    r_count = 0
    with fiona.open(src.find(src.filename)) as f:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for feature in f:
                c += 1

                if feature["properties"]["LEGER"] == "Oui":
                    mp = feature_to_multipoly(feature)
                    cur.execute(q, {"light_shape": mp.wkt, "db_srid": settings.SRID})

                    for bdg in cur:
                        r_count += 1
                        ids.append(bdg["id"])

                    if len(ids) % 5000 == 0:
                        remove(ids, conn)
                        ids = []

            remove(ids, conn)

    print(f"########## TOTAL REMOVED: {r_count}")


def remove(ids, conn):
    if len(ids) > 0:
        print(f"##############################")
        print(f"Remove {len(ids)}")
        del_q = "DELETE FROM batid_building WHERE id in %(ids)s"
        params = {"ids": tuple(ids)}
        with conn.cursor() as cur:
            cur.execute(del_q, params)
            conn.commit()
