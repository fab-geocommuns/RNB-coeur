import csv
import time
import uuid
from typing import TypedDict

from celery import Signature
from django.contrib.gis.geos import Point
from django.db import connection

from batid.models import Address
from batid.models import Building
from batid.services.imports import building_import_history
from batid.services.source import Source


class BalCsvRow(TypedDict):
    """ "
    Type of each BAL CSV row
    """

    uid_adresse: str
    cle_interop: str
    commune_insee: str
    commune_nom: str
    commune_deleguee_insee: str
    commune_deleguee_nom: str
    voie_nom: str
    lieudit_complement_nom: str
    numero: str
    suffixe: str
    position: str
    x: str
    y: str
    long: str
    lat: str
    cad_parcelles: str
    source: str
    date_der_maj: str
    certification_commune: "0" | "1"


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


def link_building_with_addresses(src_params):
    src = Source("bal")
    src.set_params(src_params)

    stats = {
        "found_using_point_in_shape": 0,
        "found_using_plots": 0,
        "total_rows": 0,
        "certified_rows": 0,
    }

    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            stats["total_rows"] += 1
            if row["certification_commune"] == "1":
                stats["certified_rows"] += 1

                # First, we try to find the link using the BAL point in shape
                found_using_point_in_shape = _find_link_using_point_in_shape(row)
                if found_using_point_in_shape:
                    stats["found_using_point_in_shape"] += 1
                    continue

                found_using_plots = _find_link_using_plots(row)
                if found_using_plots:
                    stats["found_using_plots"] += 1

        print(
            f"Treated {stats['certified_rows']} certified BAL addresses out of {stats['total_rows']} addresses"
        )

    return stats


def _find_link_using_point_in_shape(csv_row: BalCsvRow) -> bool:
    """
    First method: BAL point in shape
    """

    point = Point(float(csv_row["long"]), float(csv_row["lat"]))
    buildings = Building.objects.filter(shape__intersects=point, is_active=True)

    # We found only one building, we link the address to it
    if len(buildings) == 1 and not csv_row["cle_interop"] in buildings[0].addresses_id:
        buildings[0].update(
            addresses_id=[*buildings[0].addresses_id, csv_row["cle_interop"]]
        )
        return True

    return False


def _find_link_using_plots(csv_row: BalCsvRow) -> bool:
    """
    The second method: we use plots to find a single building
    """
    buffer_size = 0.0002
    min_cover_ratio = 0.75
    min_area = 35
    lng = float(csv_row["long"])
    lat = float(csv_row["lat"])

    # Find buildings using plots
    with connection.cursor() as cursor:
        q = """
            SELECT
                b.rnb_id AS rnb_id,
                st_area(st_intersection(b.shape, p.shape)) / st_area(b.shape) AS bdg_cover_ratio,
                st_area(b.shape::geography) AS bdg_area,
                b.addresses_id AS bdg_addresses
            FROM batid_plot p
            JOIN batid_building b ON b.shape AND p.shape
                AND st_intersects(p.shape, b.shape)
            WHERE p.shape
                AND ST_GeometryType(b.shape) != 'ST_Point'
                AND b.is_active = true
                AND st_intersects(p.shape, st_buffer(st_setsrid(st_makepoint(%(lng)s, %(lat)s), 4326), %(buffer_size)s))
                AND bdg_cover_ratio > %(min_cover_ratio)s
                AND bdg_area > %(min_area)s;
        """
        cursor.execute(
            q,
            {
                "lng": lng,
                "lat": lat,
                "buffer_size": buffer_size,
                "min_cover_ratio": min_cover_ratio,
                "min_area": min_area,
            },
        )
        buildings = cursor.fetchall()

    if not buildings:
        return False

    # If we have none, we skip
    if len(buildings) == 0:
        return False

    # If we have many big buildings, it is too ambiguous, we skip
    if len(buildings) > 1:
        return False

    # We check the address is not already linked to the bdg
    if csv_row["cle_interop"] in buildings[0].addresses_id:
        return False

    bdg = Building.objects.filter(rnb_id=buildings[0]["rnb_id"]).get()

    bdg.update(
        addresses_id=[csv_row["cle_interop"], *bdg.addresses_id],
    )

    return True
