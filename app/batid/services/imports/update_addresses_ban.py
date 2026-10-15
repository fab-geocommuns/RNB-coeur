import csv
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from io import StringIO

from batid.models import Address
from batid.services.geocoders import BanBatchGeocoder
from batid.services.imports.import_ban import has_city_reliable_ban_ids
from batid.services.source import Source
from django.contrib.gis.geos import Point
from django.db import connection
from django.db.models.functions import Upper
from django.db.models.lookups import In
from pyproj import Geod
from rapidfuzz.distance import Levenshtein

logger = logging.getLogger(__name__)


APOSTROPHES = ["'", "\u2018", "\u2019", "\u02bc", "\u02bb", "\u0060", "\u00b4"]

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


def _street_levenshtein(db_street: str | None, ban_street: str) -> int:
    """Levenshtein distance between two street names, once normalized and their
    street type abbreviation expanded."""
    s1 = _expand_street_abbreviations(normalize_text(db_street or ""))
    s2 = _expand_street_abbreviations(normalize_text(ban_street))
    return Levenshtein.distance(s1, s2)


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
    Mark addresses of a department found in the BAN file with still_exists=True.
    Addresses in the department but NOT in the BAN file are marked still_exists=False.
    Interop keys are compared case-insensitively, on their uppercase version: some
    keys in db are uppercase ("2A004_...", "35001_B001_00010") while the BAN file
    holds lowercase ones. The comparison relies on the
    address_cle_interop_upper_idx index on UPPER(cle_interop).
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
    """Mark a batch of addresses as still existing in the BAN (case-insensitive)."""
    upper_cle_interops = [cle_interop.upper() for cle_interop in cle_interops]
    return Address.objects.filter(In(Upper("cle_interop"), upper_cle_interops)).update(
        still_exists=True
    )


def _mark_obsolete_addresses(dpt: str, seen_cle_interops: set) -> int:
    """Mark addresses in the department that are not in the BAN file as obsolete
    (case-insensitive)."""
    upper_seen_cle_interops = {cle_interop.upper() for cle_interop in seen_cle_interops}
    # Filter addresses by department prefix (cle_interop starts with department code).
    # istartswith compares UPPER(cle_interop), which uses the same index. Corsica
    # department codes are uppercase ("2A") and keys can be "2a004_..." or "2A004_...".
    obsolete_count = (
        Address.objects.filter(
            cle_interop__istartswith=dpt,
        )
        .exclude(
            In(Upper("cle_interop"), upper_seen_cle_interops),
        )
        .update(still_exists=False)
    )

    return obsolete_count


COMPARISON_SUCCESS = "comparison_success"
COMPARISON_FAILURE = "comparison_failure"

# Closer than this to its BAN position (in meters), an address is the same as
# the BAN one, whatever its text.
COMPARISON_MAX_DISTANCE_M = 60
# With all its normalized fields matching the BAN ones, an address is the same
# as the BAN one up to this distance (in meters). Further, the interop key may
# now designate another place (e.g. after a renumbering).
COMPARISON_MAX_MATCHING_DISTANCE_M = 400
# Street names this close (Levenshtein distance, once normalized) are the same.
COMPARISON_MAX_STREET_LEVENSHTEIN = 2


def compare_addresses_with_ban_file(src_params: dict, batch_size: int = 10000) -> dict:
    """
    Compare the existing addresses (still_exists=True) of a department with the
    BAN file, and store the result without changing the address itself:
    - ban_update_flag: "comparison_success" if the address is closer than 60 m
      to its BAN position, or closer than 400 m with all its normalized fields
      matching the BAN ones, "comparison_failure" otherwise (see
      _is_comparison_success).
    - ban_update_details: the BAN address field by field, named after the
      Address fields like the geocoding details (see geocode_obsolete_addresses)
      so that a single later task can update the addresses from both, with the
      distance in meters to the BAN position, the Levenshtein distance between
      the normalized street names ("street_lev", stored even when the streets
      match) and the mismatching fields ("diffs"). Stored for failures too, to
      study them.

    Interop keys are compared case-insensitively, as in
    flag_addresses_from_ban_file: details["cle_interop"] is the key of the BAN
    file, which can differ from the address key by its case.

    Addresses with a ban_update_flag are skipped: a new run resumes where the
    previous one stopped.
    """
    dpt = src_params["dpt"]
    src = Source("ban_with_ids")
    src.set_params(src_params)

    successes = 0
    failures = 0
    file_path = src.find(src.filename)

    with open(file_path, "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        batch = []

        for row in reader:
            batch.append(row)

            if len(batch) >= batch_size:
                counts = _compare_batch(batch)
                successes += counts["successes"]
                failures += counts["failures"]
                logger.info(
                    f"[{dpt}] Batch done: {successes} successes, {failures} failures so far"
                )
                batch = []

        if batch:
            counts = _compare_batch(batch)
            successes += counts["successes"]
            failures += counts["failures"]

    os.remove(file_path)

    logger.info(
        f"[{dpt}] Comparison with the BAN file: {successes} successes, {failures} failures"
    )
    return {"dpt": dpt, "successes": successes, "failures": failures}


def _rep_match(db_rep: str | None, ban_rep: str) -> bool:
    # street_rep: case-insensitive + alias expansion (B→bis, T→ter, Q→quater)
    return _normalize_rep(db_rep) == _normalize_rep(ban_rep)


def _normalize_rep(street_rep: str | None) -> str:
    """Lowercase street_rep with its aliases expanded. Some addresses in db hold
    the string "null" instead of a null value: it is normalized to ""."""
    street_rep = (street_rep or "").strip().lower()
    if street_rep == "null":
        return ""
    return STREET_REP_ALIASES.get(street_rep, street_rep)


def _get_field_diffs(addr: Address, ban: dict, street_lev: int) -> dict:
    """Compare all address fields between DB and BAN data. street_lev is the
    Levenshtein distance between the normalized street names.

    Returns an empty dict if all fields match, or a dict of mismatched fields
    with their DB and BAN values.
    """
    diffs = {}
    # Text fields: normalize (strip + lower + remove accents)
    if street_lev > COMPARISON_MAX_STREET_LEVENSHTEIN:
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


def _compare_batch(rows: list) -> dict:
    """Compare a batch of BAN file rows with the matching addresses and flag
    each address."""
    ban_rows = {row["id"].upper(): row for row in rows}

    addresses = list(
        Address.objects.filter(
            In(Upper("cle_interop"), list(ban_rows.keys())),
            still_exists=True,
            ban_update_flag__isnull=True,
        )
    )

    successes = 0
    for addr in addresses:
        ban = ban_rows[addr.cle_interop.upper()]

        distance_m = _calculate_distance(addr.point, ban["lon"], ban["lat"])
        street_lev = _street_levenshtein(addr.street, ban["nom_voie"])
        diffs = _get_field_diffs(addr, ban, street_lev)

        if _is_comparison_success(distance_m, diffs):
            addr.ban_update_flag = COMPARISON_SUCCESS
            successes += 1
        else:
            addr.ban_update_flag = COMPARISON_FAILURE

        addr.ban_update_details = {
            **_ban_file_details(ban),
            "distance_m": round(distance_m, 2) if distance_m is not None else None,
            "street_lev": street_lev,
            "diffs": diffs,
        }

    if addresses:
        Address.objects.bulk_update(
            addresses, ["ban_update_flag", "ban_update_details"]
        )

    return {"successes": successes, "failures": len(addresses) - successes}


def _is_comparison_success(distance_m: float | None, diffs: dict) -> bool:
    """Whether an address is the same as its BAN one: closer than 60 m whatever
    its text, or closer than 400 m with all its normalized fields matching. The
    distance is required: without a point, the address is not checkable."""
    if distance_m is None:
        return False

    if distance_m < COMPARISON_MAX_DISTANCE_M:
        return True

    return not diffs and distance_m < COMPARISON_MAX_MATCHING_DISTANCE_M


def _ban_file_details(ban: dict) -> dict:
    """A BAN file row, field by field, named after the Address fields. Empty
    values are None."""
    return {
        "cle_interop": ban["id"],
        "ban_id": ban.get("id_ban_adresse") or None,
        "street_number": ban["numero"] or None,
        "street_rep": ban["rep"] or None,
        "street": ban["nom_voie"] or None,
        "city_zipcode": ban["code_postal"] or None,
        "city_name": ban["nom_commune"] or None,
        "city_insee_code": ban["code_insee"] or None,
        "lon": _float_or_none(ban.get("lon")),
        "lat": _float_or_none(ban.get("lat")),
    }


def delete_unlinked_obsolete_addresses(batch_size: int = 10000) -> dict:
    """Delete obsolete addresses (still_exists=False) that are not linked
    to any building (current or historical).

    The link is checked on addresses_internal_id (bigint[]) against
    batid_address.internal_id (bigint), so that the @> operator can use the
    GIN indexes on addresses_internal_id (batid_building and
    batid_building_history).

    Obsolete addresses are walked once, in internal_id order (keyset
    pagination): each batch takes the next batch_size obsolete addresses after
    the last internal_id seen and deletes the unlinked ones. Linked addresses
    are thus checked only once, instead of being checked again by every batch.

    Warning: the protection trigger is disabled during the run, so this relies
    on addresses_internal_id being complete on both tables.
    """
    total_deleted = 0
    # internal_id is drawn from a sequence starting at 1
    last_internal_id = 0

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
                    WITH batch AS (
                        SELECT internal_id FROM batid_address
                        WHERE still_exists = False AND internal_id > %s
                        ORDER BY internal_id
                        LIMIT %s
                    ), deleted AS (
                        DELETE FROM batid_address a
                        USING batch
                        WHERE a.internal_id = batch.internal_id
                        AND NOT EXISTS (
                            SELECT 1 FROM batid_building_with_history b
                            WHERE b.addresses_internal_id @> ARRAY[a.internal_id]
                        )
                        RETURNING 1
                    )
                    SELECT (SELECT max(internal_id) FROM batch),
                           (SELECT count(*) FROM deleted)
                    """,
                    [last_internal_id, batch_size],
                )
                batch_last_internal_id, deleted = cursor.fetchone()

            # Stop when no obsolete address is left after last_internal_id. A batch
            # can delete nothing (all its addresses are linked) and still not be
            # the last one.
            if batch_last_internal_id is None:
                break

            last_internal_id = batch_last_internal_id
            total_deleted += deleted
            logger.info(
                f"Deleted {deleted} unlinked obsolete addresses (batch up to "
                f"internal_id {last_internal_id}, {total_deleted} so far)"
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE batid_address ENABLE TRIGGER prevent_delete_linked_address_trigger"
            )

    logger.info(f"Total deleted unlinked obsolete addresses: {total_deleted}")
    return {"deleted_addresses": total_deleted}


GEOCODING_SUCCESS = "geocoding_success"
GEOCODING_FAILURE = "geocoding_failure"

# A housenumber result is a success if it is closer to the obsolete address than
# one of these distances (in meters) with a score above the matching minimum: the
# further the result, the higher the score must be. None: whatever the score.
GEOCODING_SUCCESS_TIERS: list[tuple[int, float | None]] = [
    (3, None),
    (20, 0.55),
    (50, 0.7),
    (150, 0.85),
    (300, 0.9),
]
# A result with a repetition index (bis, ter, a...) on one side only (the obsolete
# address or the result) is a failure, unless it is this close with this score.
GEOCODING_SUFFIX_MISMATCH_MAX_DISTANCE_M = 10
GEOCODING_SUFFIX_MISMATCH_MIN_SCORE = 0.85

GEOCODING_RESULT_COLUMNS = [
    "result_id",
    "result_banId",
    "result_type",
    "result_score",
    "result_label",
    "result_housenumber",
    "result_street",
    "result_postcode",
    "result_city",
    "result_citycode",
    "longitude",
    "latitude",
]


def geocode_obsolete_addresses(batch_size: int = 1000) -> dict:
    """
    Geocode the obsolete addresses (still_exists=False) still in db, i.e. the
    ones linked to a building once delete_unlinked_obsolete_addresses has run,
    and store the result without changing the address itself:
    - ban_update_flag: "geocoding_success" or "geocoding_failure"
    - ban_update_details: the geocoded address field by field, named after the
      Address fields so that the address can later be updated from it, with the
      geocoding score, the result type and the distance in meters to the
      obsolete address. Stored for failures too, to study them.

    Addresses are walked in internal_id order (keyset pagination). Geocoded
    addresses get a ban_update_flag and are skipped by the next runs: a new run
    resumes where the previous one stopped.
    """
    geocoder = BanBatchGeocoder()
    last_internal_id = 0
    successes = 0
    failures = 0

    while True:
        addresses = list(
            Address.objects.filter(
                still_exists=False,
                ban_update_flag__isnull=True,
                internal_id__gt=last_internal_id,
            ).order_by("internal_id")[:batch_size]
        )
        if not addresses:
            break

        last_internal_id = addresses[-1].internal_id
        results = _geocode_addresses(geocoder, addresses)

        batch_successes = 0
        for addr in addresses:
            details = _geocoding_details(addr, results.get(addr.internal_id, {}))
            if _is_geocoding_success(addr, details):
                addr.ban_update_flag = GEOCODING_SUCCESS
                batch_successes += 1
            else:
                addr.ban_update_flag = GEOCODING_FAILURE
            addr.ban_update_details = details

        Address.objects.bulk_update(
            addresses, ["ban_update_flag", "ban_update_details"]
        )

        successes += batch_successes
        failures += len(addresses) - batch_successes
        logger.info(
            f"Geocoded obsolete addresses up to internal_id {last_internal_id}: "
            f"{successes} successes, {failures} failures so far"
        )

    logger.info(
        f"Geocoding of obsolete addresses done: {successes} successes, {failures} failures"
    )
    return {"geocoding_successes": successes, "geocoding_failures": failures}


def _geocode_addresses(geocoder: BanBatchGeocoder, addresses: list) -> dict:
    """Geocode a batch of addresses. Returns the geocoder result rows by address
    internal_id."""
    data = [
        {
            "internal_id": addr.internal_id,
            "numero": addr.street_number or "",
            # Sent apart from the number: "11" and "11 b" are two different
            # addresses
            "rep": addr.street_rep or "",
            "voie": addr.street or "",
            "postcode": addr.city_zipcode or "",
            "city": addr.city_name or "",
            "citycode": addr.city_insee_code or "",
        }
        for addr in addresses
    ]

    response = geocoder.geocode(
        data=data,
        columns=["numero", "rep", "voie", "postcode", "city"],
        citycode_col="citycode",
        result_columns=GEOCODING_RESULT_COLUMNS,
    )
    response.raise_for_status()

    reader = csv.DictReader(StringIO(response.text))
    return {int(row["internal_id"]): row for row in reader}


def _geocoding_details(addr: Address, row: dict) -> dict:
    """The geocoding result of an address, field by field. Empty values are None."""
    street_number, street_rep = _split_housenumber(row.get("result_housenumber"))
    distance_m = _calculate_distance(
        addr.point, row.get("longitude", ""), row.get("latitude", "")
    )

    return {
        "cle_interop": row.get("result_id") or None,
        "ban_id": row.get("result_banId") or None,
        "street_number": street_number,
        "street_rep": street_rep,
        "street": row.get("result_street") or None,
        "city_zipcode": row.get("result_postcode") or None,
        "city_name": row.get("result_city") or None,
        "city_insee_code": row.get("result_citycode") or None,
        "lon": _float_or_none(row.get("longitude")),
        "lat": _float_or_none(row.get("latitude")),
        "label": row.get("result_label") or None,
        "type": row.get("result_type") or None,
        "score": _float_or_none(row.get("result_score")),
        "distance_m": round(distance_m, 2) if distance_m is not None else None,
    }


def _split_housenumber(housenumber: str | None) -> tuple[str | None, str | None]:
    """Split a geocoder housenumber ("11B", "11 bis", "11") into the number and
    its suffix."""
    housenumber = (housenumber or "").strip()
    if not housenumber:
        return None, None

    match = re.fullmatch(r"(\d+)\s*(\S.*)?", housenumber)
    if not match:
        return housenumber, None

    return match.group(1), match.group(2)


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _is_geocoding_success(addr: Address, details: dict) -> bool:
    """Whether the geocoding result of an obsolete address can replace it. The
    distance is required: without a point, the obsolete address is not checkable."""
    distance_m = details["distance_m"]
    if (
        details["type"] != "housenumber"
        or not details["cle_interop"]
        or distance_m is None
    ):
        return False

    score = details["score"] or 0

    if _has_suffix(addr.street_rep) != _has_suffix(details["street_rep"]) and not (
        distance_m < GEOCODING_SUFFIX_MISMATCH_MAX_DISTANCE_M
        and score > GEOCODING_SUFFIX_MISMATCH_MIN_SCORE
    ):
        return False

    return any(
        distance_m < max_distance_m and (min_score is None or score > min_score)
        for max_distance_m, min_score in GEOCODING_SUCCESS_TIERS
    )


def _has_suffix(street_rep: str | None) -> bool:
    """Whether a street_rep holds a repetition index. Some addresses in db hold
    the string "null" instead of a null value."""
    street_rep = (street_rep or "").strip()
    return bool(street_rep) and street_rep.lower() != "null"


def update_addresses_from_ban_comparison(batch_size: int = 1000) -> dict:
    """
    Update the addresses flagged "comparison_success" and not done yet with
    the BAN address stored in their ban_update_details:
    - cle_interop, street_number, street_rep, street, city_name,
      city_zipcode and city_insee_code are overwritten, empty values included;
    - point is updated only if lon and lat are both known;
    - ban_id is updated only if the BAN ids of the city (city_insee_code of the
      details) are reliable;
    - source is set to "BAN", still_exists and ban_update_done to True.
    ban_update_flag and ban_update_details are kept.

    cle_interop and ban_id are unique: a conflict raises an IntegrityError,
    which aborts the batch and the run.

    Updated addresses get ban_update_done=True, so every batch only holds
    addresses not done yet and a new run resumes where the previous one
    stopped.
    """
    updated = 0

    while True:
        addresses = list(
            Address.objects.filter(ban_update_flag=COMPARISON_SUCCESS).exclude(
                ban_update_done=True
            )[:batch_size]
        )
        if not addresses:
            break

        now = datetime.now(timezone.utc)
        for addr in addresses:
            _apply_ban_details(addr, now)

        Address.objects.bulk_update(
            addresses,
            [
                "cle_interop",
                "street_number",
                "street_rep",
                "street",
                "city_name",
                "city_zipcode",
                "city_insee_code",
                "point",
                "ban_id",
                "source",
                "still_exists",
                "ban_update_done",
                "updated_at",
            ],
        )

        updated += len(addresses)
        logger.info(f"Updated {updated} addresses from their BAN details so far")

    logger.info(f"Update of addresses from their BAN details done: {updated} updated")
    return {"updated": updated}


def _apply_ban_details(addr: Address, now: datetime) -> None:
    """Copy the BAN address stored in ban_update_details onto the address."""
    details = addr.ban_update_details

    addr.cle_interop = details["cle_interop"]
    addr.street_number = details["street_number"]
    addr.street_rep = details["street_rep"]
    addr.street = details["street"]
    addr.city_name = details["city_name"]
    addr.city_zipcode = details["city_zipcode"]
    addr.city_insee_code = details["city_insee_code"]

    if details["lon"] is not None and details["lat"] is not None:
        addr.point = Point(details["lon"], details["lat"], srid=4326)

    if (
        details["ban_id"]
        and details["city_insee_code"]
        and has_city_reliable_ban_ids(details["city_insee_code"])
    ):
        addr.ban_id = details["ban_id"]

    addr.source = "BAN"
    addr.still_exists = True
    addr.ban_update_done = True
    # bulk_update does not apply auto_now
    addr.updated_at = now
