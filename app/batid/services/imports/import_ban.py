import csv
from typing import Optional
import uuid

from celery import Signature
from django.contrib.gis.geos import Point

from batid.models import Address
from batid.services.imports import building_import_history
from batid.services.source import Source


def create_ban_full_import_tasks(dpt_list: list) -> list:

    tasks = []

    bulk_launch_uuid = str(uuid.uuid4())

    for dpt in dpt_list:

        dpt_tasks = _create_ban_dpt_import_tasks(dpt, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    return tasks


def _create_ban_dpt_import_tasks(dpt: str, bulk_launch_id=None) -> list:

    tasks = []
    src_params = {
        "dpt": dpt,
    }

    # 1) We download the BAN file
    dl_task = Signature(
        "batid.tasks.dl_source",
        args=["ban", src_params],
        immutable=True,
    )
    tasks.append(dl_task)

    task = Signature(
        "batid.tasks.import_ban", args=[src_params, bulk_launch_id], immutable=True
    )
    tasks.append(task)

    return tasks


def import_ban_addresses(
    src_params: dict,
    bulk_launch_uuid: Optional[str] = None,
    batch_size: Optional[int] = 100000,
):

    # First, we register the import
    if bulk_launch_uuid:
        building_import_history.insert_building_import(
            "bal", bulk_launch_uuid, src_params["dpt"]
        )

    src = Source("ban")
    src.set_params(src_params)

    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")

        addresses_batch = []
        adresses_count = 0

        for row in reader:

            addresses_batch.append(
                Address(
                    id=row["id"],
                    source="Import BAN",
                    point=Point(float(row["lon"]), float(row["lat"]), srid=4326),
                    street_number=row["numero"],
                    street_rep=row["rep"],
                    street=row["nom_voie"],
                    city_name=row["nom_commune"],
                    city_zipcode=row["code_postal"],
                    city_insee_code=row["code_insee"],
                )
            )

            if len(addresses_batch) >= batch_size:
                Address.objects.bulk_create(addresses_batch, ignore_conflicts=True)
                addresses_batch = []

        Address.objects.bulk_create(addresses_batch, ignore_conflicts=True)

    return f"Imported {adresses_count} BAN addresses"
