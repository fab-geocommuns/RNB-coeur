import csv
import logging
import os

from django.db import connection

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

            batch.append({"cle_interop": cle_interop})
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


def _update_batch(batch: list) -> int:
    """Update a batch of addresses."""
    cle_interops = [item["cle_interop"] for item in batch]
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


def delete_unlinked_obsolete_addresses(batch_size: int = 10000) -> int:
    """Delete obsolete addresses (still_exists=False) that are not linked
    to any building (current or historical).

    Uses the @> operator to leverage the GIN index on addresses_id.
    """
    total_deleted = 0

    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE batid_address DISABLE TRIGGER delete_address_id_from_building_trigger"
        )
    try:
        while True:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM batid_address
                    WHERE id IN (
                        SELECT a.id FROM batid_address a
                        WHERE a.still_exists = False
                        AND NOT EXISTS (
                            SELECT 1 FROM batid_building_with_history b
                            WHERE b.addresses_id @> ARRAY[a.id]
                        )
                        LIMIT %s
                    )
                    """,
                    [batch_size],
                )
                deleted = cursor.rowcount

            if deleted == 0:
                break

            total_deleted += deleted
            logger.info(f"Deleted {deleted} unlinked obsolete addresses (batch)")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE batid_address ENABLE TRIGGER delete_address_id_from_building_trigger"
            )

    logger.info(f"Total deleted unlinked obsolete addresses: {total_deleted}")
    return total_deleted
