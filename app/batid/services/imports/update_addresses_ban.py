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
    """
    dpt = src_params["dpt"]
    src = Source("ban_with_ids")
    src.set_params(src_params)

    updated_count = 0
    file_path = src.find(src.filename)

    with open(file_path, "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        batch = []

        for row in reader:
            cle_interop = row["id"]
            ban_id_str = row.get("id_ban_adresse", "")

            ban_id = _parse_uuid(ban_id_str)
            batch.append({"cle_interop": cle_interop, "ban_id": ban_id})

            if len(batch) >= batch_size:
                updated_count += _update_batch(batch)
                batch = []

        if batch:
            updated_count += _update_batch(batch)

    # Clean up the file
    os.remove(file_path)

    logger.info(f"[{dpt}] Updated {updated_count} addresses")
    return {"dpt": dpt, "updated": updated_count}


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
