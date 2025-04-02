from datetime import datetime
from datetime import timezone

from django.conf import settings
from django.core.serializers import serialize
from django.db import connection
from django.db.models import QuerySet
from psycopg2.extras import RealDictCursor

from batid.models import Building
from batid.models import City
from batid.models import Department
from batid.services.bdg_status import BuildingStatus
from batid.services.source import Source


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


def export_city(insee_code: str) -> str:
    src = Source("export")
    src.set_param("city", insee_code)
    src.set_param("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    city = City.objects.get(code_insee=insee_code)

    # NB : filtrer pour ne conserver que les bâtiments réels
    bdgs = Building.objects.filter(shape__intersects=city.shape).order_by("rnb_id")

    geojson = serialize(
        "geojson",
        bdgs,
        geometry_field="shape",
        fields=("rnb_id", "status", "ext_ids"),
    )

    # remove the id field from the features
    # I would have preferred to serialize directly without the id field
    # but since Django 4.2 the id field is included.
    # https://github.com/django/django/pull/15740
    # https://stackoverflow.com/questions/1615649/remove-pk-field-from-django-serialized-objects
    import json

    data = json.loads(geojson)
    for f in data["features"]:
        del f["id"]
    geojson = json.dumps(data)

    with open(src.path, "w") as f:
        f.write(geojson)

    return src.path


def get_real_bdgs_queryset() -> QuerySet:

    return Building.objects.filter(
        status__in=BuildingStatus.REAL_BUILDINGS_STATUS, is_active=True
    )
