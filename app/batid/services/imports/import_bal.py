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
from batid.models import BuildingWithHistory
from batid.services.building import get_real_bdgs_queryset
from batid.services.source import Source
from batid.services.imports import building_import_history


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

            current_bdg_addresses = bdg_to_link.addresses_id
            current_bdg_addresses.append(row["cle_interop"])

            bdg_to_link.update(
                user=None,
                event_origin={"source": "import", "id": building_import.id},
                addresses_id=current_bdg_addresses,
            )
            updates += 1

        building_import.building_updated_count = updates
        building_import.save()


def find_bdg_to_link(address_point: Point, cle_interop: str) -> Optional[Building]:

    bdgs = get_real_bdgs_queryset()
    bdgs = bdgs.annotate(distance=Distance("shape", address_point)).filter(
        distance__lte=D(m=3)
    )

    # We do NOT want to create the bdg <> address link if the same link exists or has existed in the past
    # To do so:
    # - We build an array of all past and present addresses id for each building (via annotate() and the subquery)
    # - We then verify if the "cle_interop" is not in this list of historical addresses

    historical_addresses_subquery = BuildingWithHistory.objects.filter(
        rnb_id=OuterRef("rnb_id")
    ).annotate(address_id=RawSQL("unnest(addresses_id)", ()))

    bdgs = bdgs.annotate(
        historical_addresses=AddressesInHistory(historical_addresses_subquery)
    )

    if bdgs.count() == 1:

        historical_addresses = bdgs.first().historical_addresses

        # There is no historical address, we can link
        if historical_addresses is None or len(historical_addresses) == 0:
            return bdgs.first()
        # There are historical addresses but the current one is not in the list
        elif historical_addresses and cle_interop not in historical_addresses:
            return bdgs.first()

    return None


class AddressesInHistory(Subquery):
    template = "(SELECT array_agg(_agg.address_id) FROM (%(subquery)s) AS _agg)"
