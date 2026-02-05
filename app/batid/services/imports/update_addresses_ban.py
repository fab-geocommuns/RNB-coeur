import csv
import logging
import os
import uuid
from typing import Optional

from batid.models import Address
from batid.services.source import Source

logger = logging.getLogger(__name__)


def flag_addresses_from_ban_file(src_params: dict, batch_size: int = 10000) -> dict:
    """
    Update addresses for a department with still_exists=True
    and their ban_id from the BAN file.
    Addresses in the department but NOT in the BAN file are marked still_exists=False.
    """
    dpt = src_params["dpt"]
    src = Source("ban_with_ids")
    src.set_params(src_params)

    updated_count = 0
    seen_cle_interops: set[str] = set()
    file_path = src.find(src.filename)

    with open(file_path, "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        batch = []

        for row in reader:
            cle_interop = row["id"]
            ban_id_str = row.get("id_ban_adresse", "")

            ban_id = _parse_uuid(ban_id_str)
            batch.append({"cle_interop": cle_interop, "ban_id": ban_id})
            seen_cle_interops.add(cle_interop)

            if len(batch) >= batch_size:
                updated_count += _update_batch(batch)
                batch = []

        if batch:
            updated_count += _update_batch(batch)

    # Clean up the file
    os.remove(file_path)

    # Mark addresses not in BAN as still_exists=False
    obsolete_count = _mark_obsolete_addresses(dpt, seen_cle_interops)

    logger.info(
        f"[{dpt}] Updated {updated_count} addresses, marked {obsolete_count} as obsolete"
    )
    return {"dpt": dpt, "updated": updated_count, "obsolete": obsolete_count}


def _parse_uuid(value: str) -> Optional[uuid.UUID]:
    """Parse a UUID string, return None if invalid."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        logger.warning(f"Invalid UUID: {value}")
        return None


def _update_batch(batch: list) -> int:
    """Update a batch of addresses."""
    cle_interops = [item["cle_interop"] for item in batch]
    ban_ids_map = {item["cle_interop"]: item["ban_id"] for item in batch}

    addresses = list(Address.objects.filter(id__in=cle_interops))

    for addr in addresses:
        addr.still_exists = True
        addr.ban_id = ban_ids_map.get(addr.id)

    if addresses:
        Address.objects.bulk_update(addresses, ["still_exists", "ban_id"])

    return len(addresses)


def _mark_obsolete_addresses(dpt: str, seen_cle_interops: set) -> int:
    """Mark addresses in the department that are not in the BAN file as obsolete."""
    # Filter addresses by department prefix (cle_interop starts with department code)
    obsolete_count = (
        Address.objects.filter(
            id__startswith=dpt,
        )
        .exclude(
            id__in=seen_cle_interops,
        )
        .update(still_exists=False)
    )

    return obsolete_count
