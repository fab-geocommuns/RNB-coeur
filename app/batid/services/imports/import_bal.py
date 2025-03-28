from typing import Optional

from celery import Signature
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

from batid.models import Building
from batid.services.building import get_real_bdgs_queryset


def create_all_bal_links_tasks(dpts: list):

    tasks = []

    for dpt in dpts:
        dpt_tasks = _create_bal_links_dpt_tasks(dpt)
        tasks.extend(dpt_tasks)

    return tasks


def _create_bal_links_dpt_tasks(dpt: str):

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
        "batid.tasks.create_dpt_bal_rnb_links", args=[src_params], immutable=True
    )
    tasks.append(links_task)

    return tasks


def create_dpt_bal_rnb_links(dpt: str):

    pass


def bdg_to_link(point: Point, cle_interop: str) -> Optional[Building]:

    qs = get_real_bdgs_queryset()

    bdgs = qs.annotate(distance=Distance("shape", point)).filter(distance__lte=D(m=3))

    if bdgs.count() == 1:
        return bdgs.first()

    return None
