import csv
import json
import os
from datetime import date
from datetime import datetime
from datetime import timezone
from io import StringIO
from typing import Optional

import ijson  # type: ignore[import-untyped]
from celery import Signature
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.db import connection
from django.db import transaction

from batid.models import Plot
from batid.services.administrative_areas import dpt_list_metropole
from batid.services.administrative_areas import drom_list
from batid.services.source import Source


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
        os.remove(src.path)


def _save_plots(rows):

    f = StringIO()
    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    f.seek(0)

    with connection.cursor() as cursor:
        cursor.copy_from(
            f,
            Plot._meta.db_table,
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


def create_plots_full_import_tasks(dpt_list: list, release_date: str) -> list:

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


def etalab_recent_release_date(before: Optional[date] = None) -> str:  # type: ignore[return]
    # If no date is provided, we use the current date
    if before is None:
        before = datetime.now().date()

    # First we get an ordred list of all release dates
    release_dates = sorted(
        [
            datetime.strptime(date, "%Y-%m-%d").date()
            for date in _etalab_releases_dates()
        ]
    )

    for idx, date in enumerate(release_dates):
        if date >= before:
            # Return the previous release date
            return release_dates[idx - 1].strftime("%Y-%m-%d")


def _etalab_releases_dates() -> list:

    # It seems Etalab has change its release dates since september 2025
    

    return [
        #
        "2024-10-01",
        # In 2025, there were no release in July and October. Instead, there was a release in September.
        "2025-01-01",
        "2025-04-01",
        "2025-09-01",
        #
        "2026-01-01",
        "2026-04-01",
        "2026-07-01",
        "2026-10-01",
        #
        "2027-01-01",
        "2027-04-01",
        "2027-07-01",
        "2027-10-01",
        #
        "2028-01-01",
        "2028-04-01",
        "2028-07-01",
        "2028-10-01",
        #
        "2029-01-01",
        "2029-04-01",
        "2029-07-01",
        "2029-10-01",
        #
        "2030-01-01",
        "2030-04-01",
        "2030-07-01",
        "2030-10-01",
    ]
