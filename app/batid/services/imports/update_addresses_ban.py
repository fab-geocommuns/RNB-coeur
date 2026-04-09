import csv
import logging
import os
import unicodedata
import uuid
from datetime import datetime
from datetime import timezone
from io import StringIO

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.db import connection
from django.db import transaction
from pyproj import Geod
from rapidfuzz.distance import Levenshtein

from batid.models import Address
from batid.services.geocoders import BanBatchGeocoder
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

    still_exists_count = 0
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
                still_exists_count += _mark_existing_addresses(batch)
                batch = []

        if batch:
            still_exists_count += _mark_existing_addresses(batch)

    # Clean up the file
    os.remove(file_path)

    # Mark addresses not in BAN as still_exists=False
    obsolete_count = _mark_obsolete_addresses(dpt, seen_cle_interops)

    logger.info(
        f"[{dpt}] Confirmed existence of {still_exists_count} addresses, marked {obsolete_count} as obsolete"
    )
    return {"dpt": dpt, "still_exist": still_exists_count, "obsolete": obsolete_count}


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


def update_addresses_text_and_ban_id(src_params: dict, batch_size: int = 10000) -> dict:
    """
    For addresses with still_exists=True, compare with BAN file using distance and normalized text.
    - If distance < 20m: update all fields with BAN version (same address).
    - Else if all normalized fields match: update all fields with BAN version.
    - Else: set ban_update_flag="text_mismatch" with diff details.
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
        seen_ban_ids: set[str] = set()

        for row in reader:
            ban_id = row.get("id_ban_adresse", "")
            if ban_id and ban_id in seen_ban_ids:
                logger.warning(
                    f"[{dpt}] Duplicate ban_id in source file: {ban_id}, skipping row"
                )
                continue
            if ban_id:
                seen_ban_ids.add(ban_id)

            batch.append(
                {
                    "cle_interop": row["id"],
                    "nom_voie": row["nom_voie"],
                    "nom_commune": row["nom_commune"],
                    "numero": row["numero"],
                    "rep": row["rep"],
                    "code_postal": row["code_postal"],
                    "code_insee": row["code_insee"],
                    "id_ban_adresse": ban_id,
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


def _rep_match(db_rep: str | None, ban_rep: str) -> bool:
    # street_rep: case-insensitive + alias expansion (B→bis, T→ter, Q→quater)
    db_rep = STREET_REP_ALIASES.get(
        (db_rep or "").strip().lower(), (db_rep or "").strip().lower()
    )
    ban_rep = STREET_REP_ALIASES.get(ban_rep.strip().lower(), ban_rep.strip().lower())
    return db_rep == ban_rep


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

    if not _rep_match(addr.street_rep, ban["rep"]):
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

    addresses = list(
        Address.objects.filter(
            id__in=cle_interops, still_exists=True, ban_update_flag__isnull=True
        )
    )

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


def geocode_and_update_obsolete_addresses(batch_size: int = 8000) -> dict:
    """
    Géocode par batches toutes les adresses still_exists=False liées à un bâtiment.
    - Si score >= 0.9 et type == housenumber : MAJ cle interop + Building.addresses_id
    - Sinon : ban_update_flag = 'geocoding_failure'
    Boucle jusqu'à épuisement des adresses non traitées.
    """
    geocoder = BanBatchGeocoder()
    total_updated = 0
    total_not_found = 0

    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.street_number, a.street, a.city_zipcode, a.city_name, a.city_insee_code, a.point
                FROM batid_address a
                WHERE a.still_exists = False
                AND a.ban_update_flag IS NULL
                LIMIT %s
                """,
                [batch_size],
            )
            rows = cursor.fetchall()

        if not rows:
            break

        csv_data = [
            {
                "db_id": row[0],
                "numero": row[1] or "",
                "voie": row[2] or "",
                "postcode": row[3] or "",
                "city": row[4] or "",
                "citycode": row[5] or "",
            }
            for row in rows
        ]

        # {cle_interop: Point, ...} — raw cursor returns WKB hex, convert to GEOSGeometry
        addr_positions = {
            row[0]: GEOSGeometry(row[6]) if row[6] else None for row in rows
        }

        response = geocoder.geocode(
            data=csv_data,
            columns=["numero", "voie", "postcode", "city"],
            citycode_col="citycode",
            result_columns=[
                "result_id",
                "result_score",
                "result_type",
                "longitude",
                "latitude",
            ],
        )

        reader = csv.DictReader(StringIO(response.text))
        successes = []
        failures = []

        def _geocode_distance(old_position, row):
            return _calculate_distance(
                old_position,
                row.get("longitude", ""),
                row.get("latitude", ""),
            )

        def is_success(score, result_type, new_id, distance):
            if result_type == "housenumber" and new_id:
                if score >= 0.85:
                    return True
                if score >= 0.55 and distance and distance < 20:
                    return True
            return False

        for row in reader:
            try:
                score = float(row.get("result_score") or 0)
            except (ValueError, TypeError):
                score = 0.0
            result_type = row.get("result_type", "")
            new_id = row.get("result_id", "")
            old_id = row.get("db_id", "")
            distance = _geocode_distance(addr_positions[old_id], row)

            if is_success(score, result_type, new_id, distance):
                successes.append({"old_id": old_id, "new_id": new_id})
            else:
                failure = {"old_id": old_id, "score": score, "new_id": new_id}
                if distance is not None:
                    failure["distance_m"] = round(distance, 2)
                failures.append(failure)

        if successes:
            _apply_geocode_updates(successes)
            total_updated += len(successes)

        if failures:
            _flag_failures(failures)
            total_not_found += len(failures)

        logger.info(
            f"Geocoded batch: {len(successes)} updated, {len(failures)} not found"
        )

    logger.info(f"Total: {total_updated} updated, {total_not_found} geocoding failures")
    return {"updated": total_updated, "geocoding_failures": total_not_found}


def _apply_geocode_updates(successes: list) -> None:
    """Update addresses for successfully geocoded entries.

    Processes each (old_id → new_id) in its own transaction for debuggability.
    Disables the versioning trigger once to avoid spurious history entries.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE batid_building DISABLE TRIGGER building_versioning_trigger"
        )
    try:
        for item in successes:
            _apply_single_geocode_update(item["old_id"], item["new_id"])
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE batid_building ENABLE TRIGGER building_versioning_trigger"
            )


def _apply_single_geocode_update(old_id: str, new_id: str) -> None:
    """Apply a single address geocode update in its own transaction.

    - If new_id is unknown: create a new Address, replace old_id in buildings, delete old
    - If new_id already exists: replace old_id in buildings, delete old
    """
    if old_id == new_id:
        Address.objects.filter(id=old_id).update(
            still_exists=True, ban_update_flag=None, ban_id=None
        )
        return

    with transaction.atomic():
        new_id_exists = Address.objects.filter(id=new_id).exists()

        if not new_id_exists:
            old_addr = Address.objects.get(id=old_id)
            Address.objects.create(
                id=new_id,
                source=old_addr.source,
                point=old_addr.point,
                street_number=old_addr.street_number,
                street_rep=old_addr.street_rep,
                street=old_addr.street,
                city_name=old_addr.city_name,
                city_zipcode=old_addr.city_zipcode,
                city_insee_code=old_addr.city_insee_code,
                still_exists=True,
            )

        # Replace old_id → new_id in Building.addresses_id
        # (building_addresses_trigger keeps BuildingAddressesReadOnly in sync)
        # DISTINCT handles the case where new_id was already present
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE batid_building
                SET addresses_id = ARRAY(
                    SELECT DISTINCT unnest(
                        array_replace(addresses_id, %s, %s)
                    )
                )
                WHERE addresses_id @> ARRAY[%s::varchar]
                """,
                [old_id, new_id, old_id],
            )

            # Replace old_id → new_id in BuildingHistory
            cursor.execute(
                """
                UPDATE batid_building_history
                SET addresses_id = ARRAY(
                    SELECT DISTINCT unnest(
                        array_replace(addresses_id, %s, %s)
                    )
                )
                WHERE addresses_id @> ARRAY[%s::varchar]
                """,
                [old_id, new_id, old_id],
            )

        # Delete old address
        # (delete_address_id_from_building_trigger is a no-op since old_id
        # was already replaced in buildings above)
        Address.objects.filter(id=old_id).delete()


def _flag_failures(failures: list) -> None:
    """Mark addresses that could not be geocoded with ban_update_flag='geocoding_failure'.

    Each failure is a dict with keys: old_id, score, new_id.
    Stores score and new_id in ban_update_details.
    """
    for failure in failures:
        details = {
            "score": failure["score"],
            "new_id": failure["new_id"],
        }
        distance = failure.get("distance_m")
        if distance:
            details["distance_m"] = distance

        Address.objects.filter(id=failure["old_id"]).update(
            ban_update_flag="geocoding_failure",
            ban_update_details=details,
        )


def delete_unlinked_obsolete_addresses(batch_size: int = 10000) -> dict:
    """Delete obsolete addresses (still_exists=False) that are not linked
    to any building (current or historical).

    Uses the @> operator to leverage the GIN index on addresses_id.
    """
    total_deleted = 0

    with connection.cursor() as cursor:
        # this trigger is triggered by an address deletion : it checks if a Building is referencing
        # the address and blocks the address deletion if this is the case.
        # For the moment, this trigger is painfully slow, so we deactivate it because
        # we are checking manually if this address can be deleted anyway.
        cursor.execute(
            "ALTER TABLE batid_address DISABLE TRIGGER prevent_delete_linked_address_trigger"
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
                "ALTER TABLE batid_address ENABLE TRIGGER prevent_delete_linked_address_trigger"
            )

    logger.info(f"Total deleted unlinked obsolete addresses: {total_deleted}")
    return {"deleted_addresses": total_deleted}
