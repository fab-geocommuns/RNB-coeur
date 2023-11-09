import concurrent.futures
import json
from datetime import datetime

import ijson

from django.conf import settings
from django.contrib.gis.geos import Polygon, GEOSGeometry, MultiPolygon
from django.db import connection
from django.utils import timezone
from psycopg2.extras import execute_values

from batid.models import Plot
from batid.services.source import Source
from io import StringIO

# import polars as pl
import csv


def import_etalab_plots(dpt: str):
    """Import plots from Etalab"""
    print("---- Importing Etalab plots ----")

    src = Source("plot")
    src.set_param("dpt", dpt)
    batch_size = 10000

    with open(src.path) as f:
        features = ijson.items(f, "features.item", use_float=True)

        batch = []
        c = 0
        for plot in features:
            c += 1

            batch.append(plot)

            if len(batch) >= batch_size:
                __handle_batch(batch)
                batch = []

        # Final batch
        __handle_batch(batch)


def __handle_batch(batch):
    print("-- converting batch")
    rows = map(_feature_to_row, batch)
    print("-- saving batch")
    # print(len(batch))

    f = StringIO()
    print("-- create DF")

    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)

    # df = pl.DataFrame(rows)
    print("-- write csv")

    # df.write_csv(f, has_header=False)

    print("-- seaking......")

    f.seek(0)

    print("-- inserting")

    with connection.cursor() as cursor:
        cursor.copy_from(
            f,
            Plot._meta.db_table,
            columns=("id", "shape", "created_at", "updated_at"),
            sep=",",
        )

    print("-- inserted")

    # __save_batch(rows)


def csv2string(data):
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(data)
    return si.getvalue().strip("\r\n")


def __save_batch(batch):
    print("page size = 10000")
    q = f"INSERT INTO {Plot._meta.db_table} (id, shape, created_at, updated_at) VALUES %s ON CONFLICT DO NOTHING"

    with connection.cursor() as cursor:
        execute_values(cursor, q, batch, page_size=10000)


def polygon_to_multipolygon(polygon):
    return MultiPolygon(polygon)


def _feature_to_row(feature):
    if feature["geometry"]["type"] not in ["Polygon", "MultiPolygon"]:
        raise ValueError(f"Unexpected geometry type: {feature['geometry']['type']}")

    multi_poly = GEOSGeometry(json.dumps(feature["geometry"]))

    if not multi_poly.valid:
        multi_poly = multi_poly.buffer(0)

    if multi_poly.geom_type == "Polygon":
        multi_poly = polygon_to_multipolygon(multi_poly)

    now = datetime.now(timezone.utc)

    return [feature["id"], multi_poly.hexewkb.decode("ascii"), f"{now}", f"{now}"]
