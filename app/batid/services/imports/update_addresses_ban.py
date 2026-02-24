import csv
import logging
import os

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

            batch.append(cle_interop)
            seen_cle_interops.add(cle_interop)

            if len(batch) >= batch_size:
                updated_count += _mark_existing_addresses(batch)
                batch = []

        if batch:
            updated_count += _mark_existing_addresses(batch)

    # Clean up the file
    os.remove(file_path)

    # Mark addresses not in BAN as still_exists=False
    obsolete_count = _mark_obsolete_addresses(dpt, seen_cle_interops)

    logger.info(
        f"[{dpt}] Updated {updated_count} addresses, marked {obsolete_count} as obsolete"
    )
    return {"dpt": dpt, "updated": updated_count, "obsolete": obsolete_count}


def _mark_existing_addresses(cle_interops: list) -> int:
    """Update a batch of addresses."""
    addresses = list(Address.objects.filter(id__in=cle_interops))

    for addr in addresses:
        addr.still_exists = True

    if addresses:
        Address.objects.bulk_update(addresses, ["still_exists"])

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
