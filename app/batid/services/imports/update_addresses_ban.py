import csv
import logging
import os
import unicodedata
import uuid
from datetime import datetime
from datetime import timezone

from django.contrib.gis.geos import Point
from pyproj import Geod
from rapidfuzz.distance import Levenshtein

from batid.models import Address
from batid.services.source import Source

logger = logging.getLogger(__name__)


APOSTROPHES = ["'", "\u2018", "\u2019", "\u02BC", "\u02BB", "\u0060", "\u00B4"]

STREET_REP_ALIASES = {
    "b": "bis",
    "t": "ter",
    "q": "quater",
}

STREET_TYPE_ALIASES = {
    "imp": "impasse",
    "che": "chemin",
    "av": "avenue",
    "bd": "boulevard",
    "bld": "boulevard",
    "blvd": "boulevard",
    "pl": "place",
    "rte": "route",
    "all": "allee",
    "sq": "square",
    "pass": "passage",
    "res": "residence",
    "r": "rue",
    "lot": "lotissement",
    "ham": "hameau",
    "chem": "chemin",
    "sent": "sentier",
    "car": "carrefour",
    "crs": "cours",
}


def _expand_street_abbreviations(text: str) -> str:
    """Expand common French street type abbreviations (first word only)."""
    words = text.split()
    if words and words[0] in STREET_TYPE_ALIASES:
        words[0] = STREET_TYPE_ALIASES[words[0]]
    return " ".join(words)


def _streets_match(db_street: str | None, ban_street: str) -> bool:
    """Check if two street names match, allowing abbreviations and Levenshtein distance <= 2."""
    s1 = _expand_street_abbreviations(normalize_text(db_street or ""))
    s2 = _expand_street_abbreviations(normalize_text(ban_street))
    return Levenshtein.distance(s1, s2) <= 2


def normalize_text(text: str) -> str:
    """Normalize text for comparison: strip, lowercase, remove accents, normalize punctuation."""
    text = text.strip().lower()
    text = text.replace("-", " ")
    for apo in APOSTROPHES:
        text = text.replace(apo, " ")
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
                    "lon": row.get("lon", ""),
                    "lat": row.get("lat", ""),
                }
            )

            if len(batch) >= batch_size:
                counts = _update_text_batch(batch)
                updated_count += counts["updated"]
                mismatch_count += counts["mismatched"]
                logger.info(
                    f"[{dpt}] Batch done: {updated_count} updated, {mismatch_count} mismatched so far"
                )
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


def _get_field_diffs(addr: Address, ban: dict) -> dict:
    """Compare all address fields between DB and BAN data.

    Returns an empty dict if all fields match, or a dict of mismatched fields
    with their DB and BAN values.
    """
    diffs = {}
    # Text fields: normalize (strip + lower + remove accents)
    if not _streets_match(addr.street, ban["nom_voie"]):
        diffs["street"] = {"db": addr.street, "ban": ban["nom_voie"]}
    if normalize_text(addr.city_name or "") != normalize_text(ban["nom_commune"]):
        diffs["city_name"] = {"db": addr.city_name, "ban": ban["nom_commune"]}
    # street_rep: case-insensitive + alias expansion (B→bis, T→ter, Q→quater)
    db_rep = STREET_REP_ALIASES.get(
        (addr.street_rep or "").strip().lower(), (addr.street_rep or "").strip().lower()
    )
    ban_rep = STREET_REP_ALIASES.get(
        ban["rep"].strip().lower(), ban["rep"].strip().lower()
    )
    if db_rep != ban_rep:
        diffs["street_rep"] = {"db": addr.street_rep, "ban": ban["rep"]}
    # Exact comparison for codes/numbers
    if (addr.street_number or "").strip() != ban["numero"].strip():
        diffs["street_number"] = {"db": addr.street_number, "ban": ban["numero"]}
    if (addr.city_zipcode or "").strip() != ban["code_postal"].strip():
        diffs["city_zipcode"] = {"db": addr.city_zipcode, "ban": ban["code_postal"]}
    if (addr.city_insee_code or "").strip() != ban["code_insee"].strip():
        diffs["city_insee_code"] = {
            "db": addr.city_insee_code,
            "ban": ban["code_insee"],
        }
    return diffs


def _calculate_distance(db_point, lon: str, lat: str):
    """Calculate geodesic distance in meters between the DB point and BAN coordinates.

    Returns the distance in meters, or None if either point is missing.
    Uses WGS84 ellipsoid for accurate distance worldwide.
    """
    if db_point is None or not lon or not lat:
        return None
    geod = Geod(ellps="WGS84")
    _, _, dist_m = geod.inv(db_point.x, db_point.y, float(lon), float(lat))
    return dist_m


def _apply_ban_update(addr: Address, ban: dict, now: datetime) -> None:
    """Apply BAN field values to an address and flag it as updated."""
    addr.street_number = ban["numero"]
    addr.street_rep = ban["rep"] or None
    addr.city_name = ban["nom_commune"]
    addr.city_zipcode = ban["code_postal"]
    if ban["lon"] and ban["lat"]:
        addr.point = Point(float(ban["lon"]), float(ban["lat"]), srid=4326)
    addr.city_insee_code = ban["code_insee"]
    addr.street = ban["nom_voie"]
    if ban["id_ban_adresse"]:
        addr.ban_id = uuid.UUID(ban["id_ban_adresse"])
    addr.ban_update_flag = "update"
    addr.updated_at = now


def _update_text_batch(batch: list) -> dict:
    """Compare normalized text and update or flag each address."""
    ban_data = {item["cle_interop"]: item for item in batch}
    cle_interops = list(ban_data.keys())

    addresses = list(Address.objects.filter(id__in=cle_interops, still_exists=True))

    updated = 0
    mismatched = 0
    to_update = []

    now = datetime.now(timezone.utc)

    for addr in addresses:
        ban = ban_data[addr.id]

        distance_m = _calculate_distance(addr.point, ban["lon"], ban["lat"])
        diffs = _get_field_diffs(addr, ban)

        if distance_m is not None and distance_m < 20:
            # Close enough: same address, proceed with update
            _apply_ban_update(addr, ban, now)
            updated += 1
        elif not diffs:
            # All fields match: proceed with update
            _apply_ban_update(addr, ban, now)
            updated += 1
        else:
            # Both tests failed: flag as mismatch with distance
            addr.ban_update_flag = "text_mismatch"
            if distance_m is not None:
                diffs["distance_m"] = round(distance_m, 2)
            addr.ban_update_details = diffs
            mismatched += 1

        to_update.append(addr)

    if to_update:
        Address.objects.bulk_update(
            to_update,
            [
                "point",
                "street_number",
                "street",
                "street_rep",
                "city_name",
                "city_zipcode",
                "city_insee_code",
                "ban_id",
                "ban_update_flag",
                "ban_update_details",
                "updated_at",
            ],
        )

    return {"updated": updated, "mismatched": mismatched}
