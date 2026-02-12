import csv
import logging
import time
import uuid
from typing import Optional

from celery import Signature
from django.contrib.gis.geos import Point
from django.db import connection
from django.db import transaction

from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadRequest
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.models import Building
from batid.models import BuildingImport
from batid.services.bdg_status import BuildingStatus
from batid.services.imports import building_import_history
from batid.services.source import Source
from batid.utils.db import dictfetchall

logger = logging.getLogger(__name__)


def create_all_bal_links_tasks(dpts: list, batch_size: int = 1000):

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpts:
        dpt_tasks = _create_bal_links_dpt_tasks(dpt, bulk_launch_uuid, batch_size)
        tasks.append(dpt_tasks)

    return tasks


def _create_bal_links_dpt_tasks(
    dpt: str, bulk_launch_uuid=None, batch_size: int = 1000
):

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
        args=[src_params, bulk_launch_uuid, batch_size],  # type: ignore[arg-type]
        immutable=True,
    )
    tasks.append(links_task)

    return tasks


def create_dpt_bal_rnb_links(
    src_params: dict, bulk_launch_uuid=None, batch_size: int = 1000
):

    dpt = src_params["dpt"]
    logger.info("BAL import dpt %s: starting (batch_size=%d)", dpt, batch_size)

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

        batch = []

        for row in reader:

            if row["certification_commune"] == "0":
                continue

            address_point = Point(
                float(row["long"]),
                float(row["lat"]),
                srid=4326,
            )

            batch.append((address_point, row["cle_interop"]))
            if len(batch) >= batch_size:
                batch_num += 1
                logger.info(
                    "BAL dpt %s: processing batch #%d (%d rows)",
                    dpt,
                    batch_num,
                    len(batch),
                )
                updated, refused = process_batch(batch, building_import)
                total_updated += updated
                total_refused += refused
                batch = []

    if len(batch) > 0:
        batch_num += 1
        logger.info(
            "BAL dpt %s: processing final batch #%d (%d rows)",
            dpt,
            batch_num,
            len(batch),
        )
        updated, refused = process_batch(batch, building_import)
        total_updated += updated
        total_refused += refused

    # We remove the source file
    # os.remove(src.find(src.filename))

    logger.info(
        "BAL import dpt %s done: %d batches, %d links created, %d refused",
        dpt,
        batch_num,
        total_updated,
        total_refused,
    )

    return {
        "dpt": src_params["dpt"],
        "total_updated": total_updated,
        "total_refused": total_refused,
    }


def find_bdg_to_link(
    address_point: Point, cle_interop: str, timings: Optional[dict] = None
) -> Optional[Building]:

    with connection.cursor() as cursor:

        # Simple Intersects approach first
        t0 = time.monotonic()
        matching_rnb_id = _match_bdg_intersecting(cursor, address_point)
        if timings is not None:
            timings["match_intersecting"] += time.monotonic() - t0
            timings["count_intersecting"] += 1

        if matching_rnb_id is None:

            # There was no match
            # We try the more complex plot-based approach

            t0 = time.monotonic()
            matching_rnb_id = _match_bdg_on_plot(cursor, address_point)
            if timings is not None:
                timings["match_on_plot"] += time.monotonic() - t0
                timings["count_on_plot"] += 1

    if matching_rnb_id is None:

        # Still no match
        # We give up

        return None

    # We do NOT want to create the bdg <> address link if the same link exists or has existed in the past
    t0 = time.monotonic()
    known = _known_building_address_link(cle_interop, matching_rnb_id)
    if timings is not None:
        timings["known_link_check"] += time.monotonic() - t0
        timings["count_known_link"] += 1

    if known:
        return None

    t0 = time.monotonic()
    bdg = Building.objects.get(rnb_id=matching_rnb_id)
    if timings is not None:
        timings["bdg_get"] += time.monotonic() - t0
        timings["count_bdg_get"] += 1

    return bdg


def _match_bdg_intersecting(cursor, address_point: Point) -> Optional[str]:

    on_bdg_sql = """
        SELECT bdg.rnb_id
        FROM batid_building as bdg
        WHERE ST_Intersects(bdg.shape, %(address_point)s)
        AND bdg.status IN %(status)s
        AND bdg.is_active = TRUE
        GROUP BY bdg.rnb_id
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

    # sql = """
    #     WITH close_plots AS (
    #         SELECT shape, st_area(shape::geography) AS area
    #         FROM batid_plot
    #         WHERE st_dwithin(%(address_point)s, shape::geography, 5)
    #     ),
    #     single_plot AS (
    #         SELECT shape FROM close_plots
    #         WHERE (SELECT count(*) FROM close_plots) = 1
    #           AND area <= 50000
    #     ),
    #     bdgs_on_plot AS (
    #         SELECT bdg.rnb_id,
    #             CASE WHEN ST_Area(bdg.shape) = 0 THEN 1
    #                  ELSE ST_Area(ST_Intersection(bdg.shape, single_plot.shape)) / ST_Area(bdg.shape)
    #             END AS bdg_cover_ratio
    #         FROM batid_building AS bdg, single_plot
    #         WHERE st_intersects(bdg.shape, single_plot.shape)
    #           AND bdg.status IN %(status)s
    #           AND bdg.is_active = true
    #     )
    #     SELECT rnb_id, bdg_cover_ratio FROM bdgs_on_plot
    #     WHERE bdg_cover_ratio >= 0.5
    # """

    # rows = dictfetchall(
    #     cursor,
    #     sql,
    #     {
    #         "address_point": f"{address_point}",
    #         "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
    #     },
    # )

    # if len(rows) != 1:
    #     return None

    # if rows[0]["bdg_cover_ratio"] < 0.9:
    #     return None

    # return rows[0]["rnb_id"]

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
    address_point: Point,
    cle_interop: str,
    bdg_import_id: int,
    timings: Optional[dict] = None,
) -> Optional[Building]:

    bdg_to_link = find_bdg_to_link(address_point, cle_interop, timings)

    if isinstance(bdg_to_link, Building):

        bdg_addresses = list(bdg_to_link.addresses_id or [])  # make a shallow copy
        bdg_addresses.append(cle_interop)

        t0 = time.monotonic()
        bdg_to_link.update(
            user=None,
            event_origin={"source": "import", "id": bdg_import_id},
            addresses_id=bdg_addresses,
            status=None,
        )
        if timings is not None:
            timings["bdg_update"] += time.monotonic() - t0
            timings["count_bdg_update"] += 1

        return bdg_to_link


def process_batch(batch: list, bdg_import: BuildingImport) -> tuple[int, int]:

    start = time.monotonic()

    timings = {
        "match_intersecting": 0.0,
        "match_on_plot": 0.0,
        "known_link_check": 0.0,
        "bdg_get": 0.0,
        "bdg_update": 0.0,
        "count_intersecting": 0,
        "count_on_plot": 0,
        "count_known_link": 0,
        "count_bdg_get": 0,
        "count_bdg_update": 0,
    }

    with transaction.atomic():

        # JIT is taking too long compared to the queries cost, we disable it
        # with connection.cursor() as cursor:
        #     cursor.execute("SET jit = off")

        updated_count = 0
        refused_count = 0
        for address_point, cle_interop in batch:

            try:
                updated_bdg = find_and_update_bdg(
                    address_point, cle_interop, bdg_import.id, timings
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

    elapsed = time.monotonic() - start

    # Log timing breakdown
    def _avg(total, count):
        return (total / count * 1000) if count > 0 else 0

    logger.info(
        "Batch done: size=%d, links_created=%d, refused=%d, time=%.2fs | "
        "Avg ms/call: intersect=%.1f (%d calls), plot=%.1f (%d calls), "
        "known_link=%.1f (%d calls), bdg_get=%.1f (%d calls), "
        "bdg_update=%.1f (%d calls)",
        len(batch),
        updated_count,
        refused_count,
        elapsed,
        _avg(timings["match_intersecting"], timings["count_intersecting"]),
        timings["count_intersecting"],
        _avg(timings["match_on_plot"], timings["count_on_plot"]),
        timings["count_on_plot"],
        _avg(timings["known_link_check"], timings["count_known_link"]),
        timings["count_known_link"],
        _avg(timings["bdg_get"], timings["count_bdg_get"]),
        timings["count_bdg_get"],
        _avg(timings["bdg_update"], timings["count_bdg_update"]),
        timings["count_bdg_update"],
    )
    logger.info(
        "Batch totals (s): intersect=%.2f, plot=%.2f, known_link=%.2f, "
        "bdg_get=%.2f, bdg_update=%.2f, other=%.2f",
        timings["match_intersecting"],
        timings["match_on_plot"],
        timings["known_link_check"],
        timings["bdg_get"],
        timings["bdg_update"],
        elapsed
        - timings["match_intersecting"]
        - timings["match_on_plot"]
        - timings["known_link_check"]
        - timings["bdg_get"]
        - timings["bdg_update"],
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
