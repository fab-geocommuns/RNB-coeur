import json
from datetime import datetime

import ijson

from django.conf import settings
from django.contrib.gis.geos import Polygon, GEOSGeometry
from django.db import connection
from django.utils import timezone
from psycopg2.extras import execute_values

from batid.models import Plot
from batid.services.source import Source


def import_etalab_plots(dpt: str):
    """Import plots from Etalab"""
    print("---- Importing plots ----")

    batch_size = 10000

    s = Source("plot")
    s.set_param("dpt", dpt)
    s.download()
    s.uncompress()

    with open(s.path) as f:
        features = ijson.items(f, "features.item", use_float=True)

        batch = []

        c = 0
        for plot in features:
            c += 1
            print("plot", c)

            batch.append(_feature_to_row(plot))

            if len(batch) >= batch_size:
                __save_batch(batch)
                batch = []


def __save_batch(batch):
    q = f"INSERT INTO {Plot._meta.db_table} (id, shape, created_at, updated_at) VALUES %s ON CONFLICT DO NOTHING"

    with connection.cursor() as cursor:
        execute_values(cursor, q, batch)


def _feature_to_row(feature):
    poly = GEOSGeometry(json.dumps(feature["geometry"]))
    poly.transform(settings.DEFAULT_SRID)

    now = datetime.now(timezone.utc)

    return feature["id"], f"{poly}", now, now
