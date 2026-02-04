import csv
import os
import uuid
from typing import Optional

from celery import Signature
from django.contrib.gis.geos import Point
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


def create_dpt_bal_rnb_links(src_params: dict, bulk_launch_uuid=None):

    src = Source("bal")
    src.set_params(src_params)

    building_import = building_import_history.insert_building_import(
        "bal", bulk_launch_uuid, src_params["dpt"]
    )

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
            if len(batch) >= 1000:
                process_batch(batch, building_import)
                batch = []

    if len(batch) > 0:
        process_batch(batch, building_import)

    # We remove the source file
    os.remove(src.find(src.filename))


def find_bdg_to_link(address_point: Point, cle_interop: str) -> Optional[Building]:

    bdg = _match_bdg_intersecting(address_point)

    if bdg is None:

        bdg = _match_bdg_on_plot(address_point)

    if not isinstance(bdg, Building):
        return None

    # We do NOT want to create the bdg <> address link if the same link exists or has existed in the past
    if (
        cle_interop in bdg.current_addresses  # type: ignore[attr-defined]
        or cle_interop in bdg.past_addresses  # type: ignore[attr-defined]
    ):
        return None

    return bdg


def _match_bdg_intersecting(address_point: Point) -> Optional[Building]:

    on_bdg_sql = """
        SELECT bdg.id, bdg.rnb_id, bdg.is_active, bdg.updated_at,
        COALESCE (bdg.addresses_id, '{}') AS current_addresses,
        COALESCE(array_agg(DISTINCT unnested_address_id), '{}') AS past_addresses
        FROM batid_building as bdg
        LEFT JOIN batid_building_history as history on history.rnb_id = bdg.rnb_id
        LEFT JOIN LATERAL unnest(history.addresses_id) AS unnested_address_id ON TRUE
        WHERE ST_Intersects(bdg.shape, %(address_point)s)
        AND bdg.status IN %(status)s
        AND bdg.is_active = TRUE
        GROUP BY bdg.id, bdg.rnb_id, bdg.addresses_id, bdg.is_active, bdg.updated_at
    """

    params = {
        "address_point": f"{address_point}",
        "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
    }

    bdgs = Building.objects.raw(on_bdg_sql, params)

    if len(bdgs) != 1:
        return None

    return bdgs[0]


def _match_bdg_on_plot(address_point: Point) -> Optional[Building]:

    # Quick note on the query below:
    # We want to be SUPER conservative when linking a BAL address to a BDG via the plot.
    # There are many many edge cases where this can go wrong.
    # So we add the following constraints:
    # - The address point buffer (5m) must intersect only one plot
    # - Any building with more than 50% of its area on that plot is considered as belonging to that plot
    # - The plot must have only one building matching the above condition
    # - The matching building should have 90+% of its area on that plot
    # - The building must be active and in a "real" status

    on_plot_sql = """
            SELECT bdg.id, bdg.rnb_id, bdg.is_active, bdg.updated_at, 
            CASE WHEN ST_Area(bdg.shape) = 0 THEN 1 ELSE St_Area(ST_Intersection(bdg.shape, plot.shape)) / St_Area(bdg.shape) END AS bdg_cover_ratio,
            COALESCE (bdg.addresses_id, '{}') AS current_addresses,
            COALESCE(array_agg(DISTINCT unnested_address_id), '{}') AS past_addresses
            FROM batid_building as bdg
            JOIN batid_plot as plot ON ST_Intersects(bdg.shape, plot.shape)
            LEFT JOIN batid_building_history as history on history.rnb_id = bdg.rnb_id
            LEFT JOIN LATERAL unnest(history.addresses_id) AS unnested_address_id ON TRUE
            WHERE ST_Intersects(plot.shape, ST_Buffer(%(address_point)s, 5))
            AND (CASE WHEN ST_Area(bdg.shape) = 0 THEN 1 ELSE ST_Area(ST_Intersection(bdg.shape, plot.shape)) / ST_Area(bdg.shape) END) > 0.5
            AND bdg.status IN %(status)s
            AND bdg.is_active = TRUE
            GROUP BY bdg.id, bdg.rnb_id, bdg.addresses_id, bdg.is_active, bdg.updated_at, bdg.shape, plot.shape
            HAVING COUNT(plot.id) = 1
        """

    params = {
        "address_point": f"{address_point}",
        "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
    }

    bdgs = Building.objects.raw(on_plot_sql, params)

    if len(bdgs) != 1:
        return None

    # If the building does not have 90%+ of its area on that plot, we refuse to link it
    if bdgs[0].bdg_cover_ratio < 0.9:  # type: ignore[attr-defined]
        return None

    return bdgs[0]


def find_and_update_bdg(  # type: ignore[return]
    address_point: Point, cle_interop: str, bdg_import_id: int
) -> Optional[Building]:

    bdg_to_link = find_bdg_to_link(address_point, cle_interop)

    if isinstance(bdg_to_link, Building):

        current_addresses = bdg_to_link.current_addresses  # type: ignore[attr-defined]
        current_addresses.append(cle_interop)

        bdg_to_link.update(
            user=None,
            event_origin={"source": "import", "id": bdg_import_id},
            addresses_id=current_addresses,
            status=None,
        )

        return bdg_to_link


def process_batch(batch: list, bdg_import: BuildingImport):

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
