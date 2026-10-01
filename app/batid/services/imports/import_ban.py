import csv
import logging
import time
import uuid
from typing import Optional

import requests
from batid.models import Address, City
from batid.services.imports import building_import_history
from batid.services.source import Source
from celery import Signature
from django.contrib.gis.geos import Point
from django.core.cache import cache

logger = logging.getLogger(__name__)

BAN_LOOKUP_URL = "https://plateforme.adresse.data.gouv.fr/lookup/{insee_code}"
BAN_LOOKUP_TIMEOUT = 30
# Pause between two cities, to stay gentle with the BAN API
BAN_LOOKUP_DELAY = 0.1

RELIABLE_BAN_IDS_CACHE_TIMEOUT = 60 * 10

# The BAN lookup does not know Paris, Lyon and Marseille as cities, only their
# districts ("arrondissements"), while our City table only knows the cities.
CITIES_DISTRICTS = {
    "75056": [f"751{i:02d}" for i in range(1, 21)],
    "69123": [f"6938{i}" for i in range(1, 10)],
    "13055": [f"132{i:02d}" for i in range(1, 17)],
}
DISTRICTS_CITY = {
    district: city
    for city, districts in CITIES_DISTRICTS.items()
    for district in districts
}


def create_ban_full_import_tasks(dpt_list: list) -> list:
    tasks = []
    bulk_launch_uuid = str(uuid.uuid4())

    # First, we refresh the BAN IDs reliability of all cities
    reliability_task = Signature(  # type: ignore[var-annotated]
        "batid.tasks.update_cities_ban_ids_reliability", immutable=True
    )
    tasks.append(reliability_task)

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
    dl_task = Signature(  # type: ignore[var-annotated]
        "batid.tasks.dl_source",
        args=["ban_with_ids", src_params],  # type: ignore[arg-type]
        immutable=True,
    )
    tasks.append(dl_task)

    task = Signature(  # type: ignore[var-annotated]
        "batid.tasks.import_ban", args=[src_params, bulk_launch_id], immutable=True  # type: ignore[arg-type]
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
            "ban", bulk_launch_uuid, src_params["dpt"]
        )

    src = Source("ban_with_ids")
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
                    # Comment out id_ban import since it creates duplicates and should be treated globally
                    # ban_id=row.get("id_ban_adresse") or None,
                    ban_id=None,
                )
            )

            if len(addresses_batch) >= batch_size:  # type: ignore[operator]
                created_addresses = Address.objects.bulk_create(
                    addresses_batch, ignore_conflicts=True
                )
                adresses_count += len(created_addresses)
                addresses_batch = []

        created_addresses = Address.objects.bulk_create(
            addresses_batch, ignore_conflicts=True
        )
        adresses_count += len(created_addresses)

    return f"Imported {adresses_count} BAN addresses"


def update_all_cities_ban_ids_reliability() -> str:
    """
    Refresh the has_reliable_ban_ids column of all cities.
    A city whose check fails (BAN API error, unknown city, ...) keeps its
    previous value and does not stop the whole process.
    """
    insee_codes = City.objects.order_by("code_insee").values_list(
        "code_insee", flat=True
    )

    changed_count = 0
    failed_count = 0

    for insee_code in insee_codes.iterator():
        try:
            if update_one_city_ban_ids_reliability(insee_code):
                changed_count += 1
        except Exception as e:
            failed_count += 1
            logger.warning(
                f"[{insee_code}] BAN IDs reliability check failed, previous value kept: {e}"
            )

        time.sleep(BAN_LOOKUP_DELAY)

    return (
        f"BAN IDs reliability: {changed_count} cities changed, "
        f"{failed_count} cities failed"
    )


def update_one_city_ban_ids_reliability(insee_code: str) -> bool:
    """
    Ask the BAN whether the BAN IDs of the city are reliable and save the answer
    in the has_reliable_ban_ids column, only if the value has to change.
    Returns True if the column has been changed.
    """
    city = City.objects.defer("shape").get(code_insee=insee_code)

    # Paris, Lyon and Marseille are reliable only if all their districts are
    lookup_codes = CITIES_DISTRICTS.get(insee_code, [insee_code])
    is_reliable = all(_ban_lookup_is_reliable(code) for code in lookup_codes)

    if city.has_reliable_ban_ids == is_reliable:
        return False

    city.has_reliable_ban_ids = is_reliable
    city.save(update_fields=["has_reliable_ban_ids", "updated_at"])
    cache.delete(_reliable_ban_ids_cache_key(insee_code))

    return True


def has_city_reliable_ban_ids(insee_code: str) -> bool:
    """
    Are the BAN IDs of this city reliable? Districts codes of Paris, Lyon and
    Marseille are accepted. Cities which are unknown or have never been checked
    are considered not reliable. The answer is cached for 10 minutes.
    """
    city_insee_code = DISTRICTS_CITY.get(insee_code, insee_code)

    return cache.get_or_set(
        _reliable_ban_ids_cache_key(city_insee_code),
        lambda: _read_city_ban_ids_reliability(city_insee_code),
        timeout=RELIABLE_BAN_IDS_CACHE_TIMEOUT,
    )


def _reliable_ban_ids_cache_key(insee_code: str) -> str:
    return f"city_reliable_ban_ids_{insee_code}"


def _read_city_ban_ids_reliability(insee_code: str) -> bool:
    value = (
        City.objects.filter(code_insee=insee_code)
        .values_list("has_reliable_ban_ids", flat=True)
        .first()
    )
    return value is True


def _ban_lookup_is_reliable(insee_code: str) -> bool:
    """
    Reliability rules (see https://github.com/fab-geocommuns/RNB-coeur/issues/1037):
    - withBanId is true: reliable
    - withBanId is false and no street comes from a "bal" source: reliable
    - withBanId is false and at least one street comes from a "bal" source: not reliable
    """
    response = requests.get(
        BAN_LOOKUP_URL.format(insee_code=insee_code), timeout=BAN_LOOKUP_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()

    if data["withBanId"]:
        return True

    # "voies" mixes streets and "lieux-dits", we only look at the streets
    streets = [v for v in data.get("voies", []) if v.get("type") == "voie"]
    return not any("bal" in (street.get("sources") or []) for street in streets)
