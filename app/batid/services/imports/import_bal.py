import csv
import logging
import os
import uuid
from typing import Optional

from batid.exceptions import (
    BANAPIDown,
    BANBadRequest,
    BANBadResultType,
    BANUnknownCleInterop,
)
from batid.models import Building, BuildingImport
from batid.services.bdg_status import BuildingStatus
from batid.services.imports import building_import_history
from batid.services.source import Source
from batid.utils.db import dictfetchall
from celery import Signature
from django.contrib.gis.geos import Point
from django.db import connection, transaction

logger = logging.getLogger(__name__)


def create_all_bal_links_tasks(dpts: list):

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpts:
        dpt_tasks = _create_bal_links_dpt_tasks(dpt, bulk_launch_uuid)
        tasks.append(dpt_tasks)

    return tasks


def _create_bal_links_dpt_tasks(dpt: str, bulk_launch_uuid=None):

    tasks = []
    src_params = {
        "dpt": dpt,
    }

    # 1) We download the BAL file
    dl_task = Signature(  # type: ignore[var-annotated]
        "batid.tasks.dl_source",
        args=["bal", src_params],  # type: ignore[arg-type]
        immutable=True,
    )
    tasks.append(dl_task)

    # 2) We create links between BAL and RNB
    links_task = Signature(  # type: ignore[var-annotated]
        "batid.tasks.create_dpt_bal_rnb_links",
        args=[src_params, bulk_launch_uuid],  # type: ignore[arg-type]
        immutable=True,
    )
    tasks.append(links_task)

    return tasks


def filter_by_position(rows: list) -> list:
    """
    For each cle_interop, keep only rows whose position is "bâtiment" if any such
    row exists. Otherwise keep all rows for that cle_interop.
    """
    batiment_rows: dict[str, list] = {}
    other_rows: dict[str, list] = {}

    for row in rows:
        key = row["cle_interop"]
        if row["position"] == "bâtiment":
            batiment_rows.setdefault(key, []).append(row)
        else:
            other_rows.setdefault(key, []).append(row)

    result = []
    all_keys = set(batiment_rows) | set(other_rows)
    for key in all_keys:
        if key in batiment_rows:
            result.extend(batiment_rows[key])
        else:
            result.extend(other_rows[key])

    return result


def create_dpt_bal_rnb_links(src_params: dict, bulk_launch_uuid=None):

    dpt = src_params["dpt"]
    logger.info("BAL import dpt %s: starting", dpt)

    src = Source("bal")
    src.set_params(src_params)

    building_import = building_import_history.insert_building_import(
        "bal", bulk_launch_uuid, dpt
    )

    total_updated = 0
    total_refused = 0
    batch_num = 0

    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        certified_rows = [row for row in reader if row["certification_commune"] != "0"]

    filtered_rows = filter_by_position(certified_rows)

    batch = []

    for row in filtered_rows:

        address_point = Point(
            float(row["long"]),
            float(row["lat"]),
            srid=4326,
        )

        batch.append((address_point, row["cle_interop"]))
        if len(batch) >= 1000:
            batch_num += 1
            updated, refused = process_batch(batch, building_import)
            total_updated += updated
            total_refused += refused
            batch = []

    if len(batch) > 0:
        batch_num += 1
        updated, refused = process_batch(batch, building_import)
        total_updated += updated
        total_refused += refused

    # We remove the source file
    os.remove(src.find(src.filename))

    logger.info(
        "BAL import dpt %s done: %d batches, %d links created, %d refused",
        dpt,
        batch_num,
        total_updated,
        total_refused,
    )

    return {
        "dpt": dpt,
        "total_updated": total_updated,
        "total_refused": total_refused,
    }


def find_bdg_to_link(address_point: Point, cle_interop: str) -> Optional[Building]:

    with connection.cursor() as cursor:

        # Simple Intersects approach first
        matching_rnb_id = _match_bdg_intersecting(cursor, address_point)

        if matching_rnb_id is None:

            # There was no match
            # We try the more complex plot-based approach

            matching_rnb_id = _match_bdg_on_plot(cursor, address_point)

    if matching_rnb_id is None:

        # Still no match
        # We give up

        return None

    # We do NOT want to create the bdg <> address link if the same link exists or has existed in the past
    if _known_building_address_link(cle_interop, matching_rnb_id):
        return None

    return Building.objects.get(rnb_id=matching_rnb_id)


def _match_bdg_intersecting(cursor, address_point: Point) -> Optional[str]:

    on_bdg_sql = """
        SELECT bdg.rnb_id
        FROM batid_building as bdg
        WHERE ST_Intersects(bdg.shape, %(address_point)s)
        AND bdg.status IN %(status)s
        AND bdg.is_active = TRUE
    """

    params = {
        "address_point": f"{address_point}",
        "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
    }

    rows = dictfetchall(cursor, on_bdg_sql, params)

    if len(rows) != 1:
        return None

    return rows[0]["rnb_id"]


def _match_bdg_on_plot(cursor, address_point: Point) -> Optional[str]:
    """

    This function tries to create a link between a BAL address and a BDG via the plot.

    We want to be SUPER conservative with this approach.
    There are many many edge cases where this can go wrong.
    So we add the following constraints:
    - The address point must be within 5 meters of one and only one plot
    - Any building with more than 50% of its area on that plot is considered as belonging to that plot
    - The plot must have one and only one building matching the above condition
    - The matching building should have 90+% of its area on that plot
    - The building must be active and with a "real" status
    """

    # First, we check how many plots are nearby (within 5 meters) of the address point. If there is not exactly one, we give up immediately
    close_plots_sql = """
        select shape, st_area(shape::geography) as area
        from batid_plot
        where st_dwithin(%(address_point)s, shape::geography, 5)
    """

    plots = dictfetchall(cursor, close_plots_sql, {"address_point": f"{address_point}"})

    if len(plots) != 1:
        return None

    # We avoid plot bigger than 50_000m2
    # This value is somewhat arbitrary, we met one edge case which can be avoided by ignoring very big plots.
    if plots[0]["area"] > 50_000:
        return None

    # Second, we get all buildings intersecting the plot, and check how much of their area is on the plot.
    # If there is not exactly one building with more than 50% of its area on the plot, we give up

    plot_shape = plots[0]["shape"]

    bdgs_on_plot_sql = """
        select bdg.rnb_id,
        CASE WHEN ST_Area(bdg.shape) = 0 THEN 1 ELSE St_Area(ST_Intersection(bdg.shape, %(plot_shape)s)) / St_Area(bdg.shape) END AS bdg_cover_ratio
        from batid_building as bdg
        where st_intersects(bdg.shape, %(plot_shape)s)
        AND bdg.status IN %(status)s
        AND bdg.is_active = true
    """

    bdgs_on_plot = dictfetchall(
        cursor,
        bdgs_on_plot_sql,
        {
            "plot_shape": f"{plot_shape}",
            "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
        },
    )

    # We check how many buidldings have more than 50% of their area on the plot
    candidate_bdgs = [bdg for bdg in bdgs_on_plot if bdg["bdg_cover_ratio"] >= 0.5]

    if len(candidate_bdgs) != 1:
        return None

    # We check that the matching building has 90+% of its area on the plot, otherwise we consider the match too weak
    if candidate_bdgs[0]["bdg_cover_ratio"] < 0.9:
        return None

    return candidate_bdgs[0]["rnb_id"]


def find_and_update_bdg(  # type: ignore[return]
    address_point: Point, cle_interop: str, bdg_import_id: int
) -> Optional[Building]:

    bdg_to_link = find_bdg_to_link(address_point, cle_interop)

    if isinstance(bdg_to_link, Building):

        bdg_addresses = list(bdg_to_link.addresses_id or [])  # make a shallow copy
        bdg_addresses.append(cle_interop)

        bdg_to_link.update(
            user=None,
            event_origin={"source": "import", "id": bdg_import_id},
            addresses_id=bdg_addresses,
            status=None,
        )

        return bdg_to_link


def process_batch(batch: list, bdg_import: BuildingImport) -> tuple[int, int]:

    with transaction.atomic():

        updated_count = 0
        refused_count = 0
        for address_point, cle_interop in batch:

            try:
                updated_bdg = find_and_update_bdg(
                    address_point, cle_interop, bdg_import.id
                )

                if isinstance(updated_bdg, Building):
                    updated_count += 1
            except (
                BANUnknownCleInterop,
                BANAPIDown,
                BANBadRequest,
                BANBadResultType,
            ) as _:
                refused_count += 1
                continue

        bdg_import.building_refused_count += refused_count  # type: ignore
        bdg_import.building_updated_count += updated_count  # type: ignore
        bdg_import.save()

    logger.info(
        "Batch done: size=%d, links_created=%d, refused=%d",
        len(batch),
        updated_count,
        refused_count,
    )

    return updated_count, refused_count


def _known_building_address_link(cle_interop: str, rnb_id: str) -> bool:

    q = """
        select 1
        from batid_building_with_history as bdg
        where bdg.rnb_id = %(rnb_id)s
        and %(cle_interop)s = any(bdg.addresses_id)
    """

    params = {
        "rnb_id": rnb_id,
        "cle_interop": cle_interop,
    }

    with connection.cursor() as cursor:
        rows = dictfetchall(cursor, q, params)

    return len(rows) > 0
