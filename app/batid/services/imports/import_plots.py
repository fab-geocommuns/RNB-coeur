import csv
import json
import re
from datetime import date, datetime, timezone
from io import StringIO
from typing import Optional

import ijson  # type: ignore[import-untyped]
import requests
from batid.models import Plot
from batid.services.administrative_areas import dpt_list_metropole, drom_list
from batid.services.source import Source, remove_after_task_success
from batid.utils.db import copy_from_file
from celery import Signature
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import connection, transaction

ETALAB_CADASTRE_URL = "https://cadastre.data.gouv.fr/data/etalab-cadastre/"
ETALAB_RELEASE_LINK = re.compile(r'href="/data/etalab-cadastre/(\d{4}-\d{2}-\d{2})/"')


def import_etalab_plots(dpt: str, release_date: str, batch_size: int = 100_000):
    """Import plots from Etalab"""
    print(
        f"---- Importing Etalab plots for departement {dpt} - release date {release_date} ----"
    )

    src = Source("plot")
    src.set_param("dpt", dpt)
    src.set_param("date", release_date)

    with open(src.path) as f, transaction.atomic():

        # Deleting all plots in the dpt
        Plot.objects.filter(id__startswith=dpt).delete()

        # Then, importing the new plots
        features = ijson.items(f, "features.item", use_float=True)

        batch = []

        for feature in features:

            plot = _feature_to_row(feature)
            plot.append(release_date)

            batch.append(plot)
            if len(batch) == batch_size:
                _save_plots(batch)
                batch = []

        # some plots might remain in the batch at the end of the loop, we save them
        if batch:
            _save_plots(batch)

    # remove the file
    remove_after_task_success(src.path)


def _save_plots(rows):

    f = StringIO()
    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    f.seek(0)

    with connection.cursor() as cursor:
        copy_from_file(
            cursor=cursor,
            file=f,
            table=Plot._meta.db_table,
            columns=("id", "shape", "created_at", "updated_at", "source_version"),
            sep=",",
        )


def polygon_to_multipolygon(polygon):
    return MultiPolygon(polygon)


def _feature_to_row(feature: dict):
    if feature["geometry"]["type"] not in ["Polygon", "MultiPolygon"]:
        raise ValueError(f"Unexpected geometry type: {feature['geometry']['type']}")

    multi_poly = GEOSGeometry(json.dumps(feature["geometry"]))

    if not multi_poly.valid:
        multi_poly = multi_poly.buffer(0)

    if multi_poly.geom_type == "Polygon":
        multi_poly = polygon_to_multipolygon(multi_poly)

    now = datetime.now(timezone.utc)

    return [
        feature["id"],
        multi_poly.hexewkb.decode("ascii"),
        f"{now}",
        f"{now}",
    ]


def etalab_dpt_list() -> list:

    return dpt_list_metropole() + drom_list()


def create_plots_full_import_tasks(*, dpt_list: list, release_date: str) -> list:

    tasks = []

    for dpt in dpt_list:

        # Download the plots
        dl_task = Signature(  # type: ignore[var-annotated]
            "batid.tasks.dl_source",
            args=["plot", {"dpt": dpt, "date": release_date}],  # type: ignore[arg-type]
            immutable=True,
        )
        tasks.append(dl_task)

        # Import the plots
        import_task = Signature(  # type: ignore[var-annotated]
            "batid.tasks.import_plots",
            args=[dpt, release_date],  # type: ignore[arg-type]
            immutable=True,
        )
        tasks.append(import_task)

    return tasks


def etalab_recent_release_date(before: Optional[date] = None) -> str:
    """Most recent Etalab release strictly before `before`, or the latest one if None."""
    return pick_release_date(release_dates=fetch_etalab_release_dates(), before=before)


def fetch_etalab_release_dates() -> list[date]:
    response = requests.get(ETALAB_CADASTRE_URL, timeout=30)
    response.raise_for_status()
    return [date.fromisoformat(d) for d in ETALAB_RELEASE_LINK.findall(response.text)]


def pick_release_date(*, release_dates: list[date], before: Optional[date]) -> str:
    candidates = [d for d in release_dates if before is None or d < before]
    if not candidates:
        raise ValueError(
            f"No Etalab cadastre release before {before} in {release_dates}"
        )
    return max(candidates).isoformat()
