import csv
import os
import time

from services.source import Source
from shapely.geometry import mapping, shape, MultiPolygon
from shapely.ops import transform
import fiona
from datetime import datetime, timezone
import psycopg2
from db import get_conn
from concurrent.futures import ProcessPoolExecutor


def import_bdtopo(dpt):
    dpt = dpt.zfill(3)

    src = Source("bdtopo")
    src.set_param("dpt", dpt)

    with fiona.open(src.find(src.filename)) as f:
        print("-- read bdtopo ")

        bdgs = []

        for feature in f:
            bdg = transform_bdtopo_feature(feature)
            bdgs.append(bdg)

        buffer_src = Source(
            "buffer",
            {
                "folder": "bdtopo",
                "filename": "bdgs-{{dpt}}.csv",
            },
        )
        buffer_src.set_param("dpt", dpt)

        cols = bdgs[0].keys()

        with open(buffer_src.path, "w") as f:
            print("-- writing buffer file --")
            writer = csv.DictWriter(f, delimiter=";", fieldnames=cols)
            writer.writerows(bdgs)

        conn = get_conn()
        with open(buffer_src.path, "r") as f, conn.cursor() as cursor:
            print("-- transfer buffer to db --")
            try:
                cursor.copy_from(f, "batid_candidate", sep=";", columns=cols)
                conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                conn.rollback()
                cursor.close()
                raise error

        print("- remove buffer")
        os.remove(buffer_src.path)


def transform_bdtopo_feature(feature) -> dict:
    multipoly = feature_to_multipoly(feature)

    # todo : handle addresses
    address_keys = []

    bdg = {
        "shape": multipoly.wkt,
        "is_light": True if feature["properties"]["LEGER"] == "Oui" else False,
        "source": "bdtopo",
        "source_id": feature["properties"]["ID"],
        "address_keys": f"{{{','.join(address_keys)}}}",
        "created_at": datetime.now(timezone.utc),
    }

    return bdg


def feature_to_multipoly(feature) -> MultiPolygon:
    shape_3d = shape(feature["geometry"])  # BD Topo provides 3D shapes
    shape_2d = transform(
        lambda x, y, z=None: (x, y), shape_3d
    )  # we convert them into 2d shapes

    return MultiPolygon([shape_2d])
