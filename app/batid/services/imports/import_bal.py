import csv
import time
import uuid

from celery import Signature
from django.contrib.gis.geos import Point
from django.db import connection

from batid.models import Address
from batid.models import Building
from batid.services.imports import building_import_history
from batid.services.source import Source


def create_bal_full_import_tasks(dpt_list: list) -> list:

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpt_list:

        dpt_tasks = _create_bal_dpt_import_tasks(dpt, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    return tasks


def _create_bal_dpt_import_tasks(dpt: str, bulk_launch_id=None) -> list:

    tasks = []
    src_params = {
        "dpt": dpt.zfill(2),
    }

    # 1) We download the BAL file (1 CSV per department)
    dl_task = Signature(
        "batid.tasks.dl_source",
        args=["bal", src_params],
        immutable=True,
    )
    tasks.append(dl_task)

    # 2) We create all certified adresses in our database
    task = Signature(
        "batid.tasks.import_bal", args=[src_params, bulk_launch_id], immutable=True
    )
    tasks.append(task)

    # 3) We update our buildings to link new adresses
    convert_task = Signature(
        "batid.tasks.link_building_addresses_using_bal",
        args=[src_params, bulk_launch_id],
        immutable=True,
    )
    tasks.append(convert_task)

    return tasks


def import_addresses(src_params: dict, bulk_launch_uuid=None):

    src = Source("bal")
    src.set_params(src_params)

    building_import_history.insert_building_import(
        "bal", bulk_launch_uuid, src_params["dpt"]
    )

    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")

        addresses_batch = []
        batch_size = 100000
        adresses_count = 0
        start_time = time.perf_counter()

        for row in reader:

            if row["certification_commune"] != "1":
                continue

            adresses_count += 1

            addresses_batch.append(
                Address(
                    id=row["cle_interop"],
                    source="BAL",
                    point=Point(float(row["long"]), float(row["lat"]), srid=4326),
                    street_number=row["numero"],
                    street_rep=row["suffixe"],
                    street=row["voie_nom"],
                    city_name=row["commune_nom"],
                    city_zipcode=None,  # FIXME: find the related zipcode from INSEE code (maybe using: https://www.data.gouv.fr/en/datasets/base-officielle-des-codes-postaux/)
                    city_insee_code=row["commune_insee"],
                )
            )

            if len(addresses_batch) >= batch_size:
                Address.objects.bulk_create(addresses_batch, ignore_conflicts=True)
                addresses_batch = []

        Address.objects.bulk_create(addresses_batch, ignore_conflicts=True)
        end_time = time.perf_counter()
        print(f"Duration: {(end_time - start_time):.2f}s")

    return f"Imported {adresses_count} BAN addresses"
