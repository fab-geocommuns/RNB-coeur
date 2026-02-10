import csv
import logging
import os
import unicodedata
import uuid

from batid.models import Address
from batid.services.source import Source

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for comparison: strip, lowercase, remove accents."""
    text = text.strip().lower()
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


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


def update_addresses_text_and_ban_id(src_params: dict, batch_size: int = 10000) -> dict:
    """
    For addresses with still_exists=True, compare normalized text with BAN file.
    - If all fields match: update street/city_name/street_rep with BAN version + set ban_id.
    - If any field differs: set ban_update_flag="text_mismatch".
    """
    dpt = src_params["dpt"]
    src = Source("ban_with_ids")
    src.set_params(src_params)

    updated_count = 0
    mismatch_count = 0
    file_path = src.find(src.filename)

    with open(file_path, "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        batch = []

        for row in reader:
            batch.append(
                {
                    "cle_interop": row["id"],
                    "nom_voie": row["nom_voie"],
                    "nom_commune": row["nom_commune"],
                    "numero": row["numero"],
                    "rep": row["rep"],
                    "code_postal": row["code_postal"],
                    "code_insee": row["code_insee"],
                    "id_ban_adresse": row.get("id_ban_adresse", ""),
                }
            )

            if len(batch) >= batch_size:
                counts = _update_text_batch(batch)
                updated_count += counts["updated"]
                mismatch_count += counts["mismatched"]
                batch = []

        if batch:
            counts = _update_text_batch(batch)
            updated_count += counts["updated"]
            mismatch_count += counts["mismatched"]

    os.remove(file_path)

    logger.info(
        f"[{dpt}] Text update: {updated_count} updated, {mismatch_count} mismatched"
    )
    return {"dpt": dpt, "updated": updated_count, "mismatched": mismatch_count}


def _fields_match(addr: Address, ban: dict) -> bool:
    """Compare all address fields between DB and BAN data."""
    # Text fields: normalize (strip + lower + remove accents)
    if normalize_text(addr.street or "") != normalize_text(ban["nom_voie"]):
        return False
    if normalize_text(addr.city_name or "") != normalize_text(ban["nom_commune"]):
        return False
    # street_rep: case-insensitive
    if (addr.street_rep or "").strip().lower() != ban["rep"].strip().lower():
        return False
    # Exact comparison for codes/numbers
    if (addr.street_number or "").strip() != ban["numero"].strip():
        return False
    if (addr.city_zipcode or "").strip() != ban["code_postal"].strip():
        return False
    if (addr.city_insee_code or "").strip() != ban["code_insee"].strip():
        return False
    return True


def _update_text_batch(batch: list) -> dict:
    """Compare normalized text and update or flag each address."""
    ban_data = {item["cle_interop"]: item for item in batch}
    cle_interops = list(ban_data.keys())

    addresses = list(Address.objects.filter(id__in=cle_interops, still_exists=True))

    updated = 0
    mismatched = 0
    to_update = []

    for addr in addresses:
        ban = ban_data[addr.id]

        if _fields_match(addr, ban):
            addr.street = ban["nom_voie"]
            addr.city_name = ban["nom_commune"]
            addr.street_rep = ban["rep"] or None
            if ban["id_ban_adresse"]:
                addr.ban_id = uuid.UUID(ban["id_ban_adresse"])
            updated += 1
        else:
            addr.ban_update_flag = "text_mismatch"
            mismatched += 1

        to_update.append(addr)

    if to_update:
        Address.objects.bulk_update(
            to_update,
            ["street", "city_name", "street_rep", "ban_id", "ban_update_flag"],
        )

    return {"updated": updated, "mismatched": mismatched}
