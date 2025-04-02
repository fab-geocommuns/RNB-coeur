import csv
import uuid
from typing import Optional

from celery import Signature
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.expressions import RawSQL

from batid.models import Building
from batid.models import BuildingHistoryOnly
from batid.services.bdg_status import BuildingStatus
from batid.services.building import get_real_bdgs_queryset
from batid.services.imports import building_import_history
from batid.services.source import Source


def create_all_bal_links_tasks(dpts: list):

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpts:
        dpt_tasks = _create_bal_links_dpt_tasks(dpt, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    return tasks


def _create_bal_links_dpt_tasks(dpt: str, bulk_launch_uuid=None):

    tasks = []
    src_params = {
        "dpt": dpt,
    }

    # 1) We download the BAL file
    dl_task = Signature(
        "batid.tasks.dl_source",
        args=["bal", src_params],
        immutable=True,
    )
    tasks.append(dl_task)

    # 2) We create links between BAL and RNB
    links_task = Signature(
        "batid.tasks.create_dpt_bal_rnb_links",
        args=[src_params, bulk_launch_uuid],
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

    updates = 0

    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:

            if row["certification_commune"] == "0":
                continue

            bdg_to_link = find_bdg_to_link(
                Point(
                    float(row["long"]),
                    float(row["lat"]),
                    srid=4326,
                ),
                row["cle_interop"],
            )

            if not isinstance(bdg_to_link, Building):
                continue

            current_bdg_addresses = (
                bdg_to_link.addresses_id
                if isinstance(bdg_to_link.addresses_id, list)
                else []
            )
            current_bdg_addresses.append(row["cle_interop"])

            bdg_to_link.update(
                user=None,
                event_origin={"source": "import", "id": building_import.id},
                addresses_id=current_bdg_addresses,
                status=None,
            )
            updates += 1

        building_import.building_updated_count = updates
        building_import.save()


def find_bdg_to_link(address_point: Point, cle_interop: str) -> Optional[Building]:

    sql = """
        SELECT bdg.id, bdg.rnb_id, 
        COALESCE (bdg.addresses_id, '{}') AS current_addresses, 
        COALESCE(array_agg(DISTINCT unnested_address_id), '{}') AS past_addresses 
        FROM batid_building as bdg
        LEFT JOIN batid_building_history as history on history.rnb_id = bdg.rnb_id
        LEFT JOIN LATERAL unnest(history.addresses_id) AS unnested_address_id ON TRUE
        WHERE ST_DWithin(bdg.shape::geography, %(address_point)s::geography, 3)
        AND bdg.status IN %(status)s
        AND bdg.is_active = TRUE
        GROUP BY bdg.id, bdg.rnb_id, bdg.addresses_id
    """

    params = {
        "address_point": f"{address_point}",
        "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
    }

    bdgs = Building.objects.raw(sql, params)

    if len(bdgs) == 1:

        # We do NOT want to create the bdg <> address link if the same link exists or has existed in the past
        if (
            cle_interop in bdgs[0].current_addresses
            or cle_interop in bdgs[0].past_addresses
        ):
            return None

        return bdgs[0]

    return None
