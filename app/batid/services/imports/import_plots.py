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


def import_etalab_plots(dpt: str):
    """Import plots from Etalab"""
    print("---- Importing plots ----")

    batch_size = 50000

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

            batch.append(plot)

            if len(batch) >= batch_size:
                __handle_batch(batch)
                batch = []

        # Final batch
        __handle_batch(batch)


def __handle_batch(batch):
    print("-- converting batch")
    with concurrent.futures.ProcessPoolExecutor() as executor:
        rows = executor.map(_feature_to_row, batch)

    print("-- saving batch")
    __save_batch(rows)


def __save_batch(batch):
    q = f"INSERT INTO {Plot._meta.db_table} (id, shape, created_at, updated_at) VALUES %s ON CONFLICT DO NOTHING"

    with connection.cursor() as cursor:
        execute_values(cursor, q, batch)


def _feature_to_row(feature):
    if feature["geometry"]["type"] not in ["Polygon", "MultiPolygon"]:
        raise ValueError(f"Unexpected geometry type: {feature['geometry']['type']}")

    if feature["geometry"]["type"] == "Polygon":
        mp_dict = {
            "type": "MultiPolygon",
            "coordinates": [feature["geometry"]["coordinates"]],
        }

    if feature["geometry"]["type"] == "MultiPolygon":
        mp_dict = feature["geometry"]

    multi_poly = GEOSGeometry(json.dumps(mp_dict))

    if multi_poly.srid != settings.DEFAULT_SRID:
        multi_poly.transform(settings.DEFAULT_SRID)

    if not multi_poly.valid:
        multi_poly = multi_poly.buffer(0)

    now = datetime.now(timezone.utc)

    return feature["id"], f"{multi_poly}", now, now
