from celery import Signature
from typing import Optional
from django.contrib.gis.geos import Point
from batid.models import Building


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

    bdgs = Building.objects.filter(shape__contains=point)

    if bdgs:
        return bdgs.first()

    return None
