import csv
import json
from datetime import datetime
from datetime import timezone
from io import StringIO

import ijson
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.db import connection, transaction

from batid.models import Plot
from batid.services.source import Source


def import_etalab_plots(dpt: str):
    """Import plots from Etalab"""
    print("---- Importing Etalab plots ----")

    src = Source("plot")
    src.set_param("dpt", dpt)

    with open(src.path) as f:
        features = ijson.items(f, "features.item", use_float=True)

        plots = map(_feature_to_row, features)

        with transaction.atomic():
            print("deleting plots with id starting with", dpt)
            Plot.objects.filter(id__startswith=dpt).delete()
            print("plots deleted")

            print("saving plots")
            _save_plots(plots)
            print("plots saved")


def _save_plots(rows):
    f = StringIO()
    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    f.seek(0)

    with connection.cursor() as cursor:
        cursor.copy_from(
            f,
            Plot._meta.db_table,
            columns=("id", "shape", "created_at", "updated_at"),
            sep=",",
        )


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


def create_plots_full_import_tasks(dpt_lists: list) -> list:
    pass
