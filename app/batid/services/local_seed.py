"""
Seed a local development database with a geographic extract of a remote RNB
database (typically the sandbox, which is a copy of the production database).

The extract is made of the buildings around one or several GPS points, the
addresses they are linked to (plus the addresses located in the same zones),
and the cities and departments touching those zones.

Personal data is not copied: no user is imported, and the building columns
referencing users (event_user_id, validated_by) are emptied.
"""

import math
import re
import tempfile
from dataclasses import dataclass

from batid.utils.db import DISABLE_BUILDING_VERSIONING_SETTING
from django.conf import settings
from django.db import connection, transaction

MAX_RADIUS_KM = 10

# Rough bounding boxes of the territories covered by the RNB:
# (name, min_lat, max_lat, min_lon, max_lon)
FRANCE_BBOXES = [
    ("France métropolitaine", 41.2, 51.2, -5.3, 9.7),
    ("Guadeloupe", 15.8, 16.6, -61.9, -60.9),
    ("Martinique", 14.3, 14.9, -61.3, -60.7),
    ("Guyane", 2.1, 5.9, -54.7, -51.5),
    ("La Réunion", -21.5, -20.8, 55.2, 55.9),
    ("Mayotte", -13.1, -12.6, 44.9, 45.4),
]

# The seed only writes into a database running next to the app, in development
LOCAL_DB_HOSTS = {"db", "localhost", "127.0.0.1"}

# Metres in one degree of latitude (and of longitude at the equator)
METERS_PER_DEGREE = 111_320


class SeedConfigError(Exception):
    pass


@dataclass(frozen=True)
class Zone:
    lat: float
    lon: float
    radius_m: float

    @property
    def radius_deg(self) -> float:
        # Upper bound of the radius in degrees, used to hit the geometry
        # spatial indexes before the exact (geography) distance check.
        # A degree of longitude shrinks with the latitude, hence the cosine.
        return (
            self.radius_m / (METERS_PER_DEGREE * math.cos(math.radians(self.lat))) * 1.1
        )


# ---------------------------------------------------------------------------
# Configuration parsing and validation
# ---------------------------------------------------------------------------


def parse_points(raw: str) -> list[tuple[float, float]]:
    """
    Parse "lat,lon;lat,lon" into a list of (lat, lon) tuples.
    """
    points = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) != 2:
            raise SeedConfigError(
                f"Point invalide « {chunk} » : format attendu « lat,lon » (ex: 48.8584,2.2945)"
            )
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            raise SeedConfigError(
                f"Point invalide « {chunk} » : coordonnées non numériques"
            )
        points.append((lat, lon))

    if not points:
        raise SeedConfigError("Aucun point fourni")

    return points


def _territory(lat: float, lon: float) -> str | None:
    for name, min_lat, max_lat, min_lon, max_lon in FRANCE_BBOXES:
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return name
    return None


def validate_point(lat: float, lon: float) -> str:
    """
    Check the point is in a territory covered by the RNB and return its name.
    """
    territory = _territory(lat, lon)
    if territory:
        return territory

    message = f"Le point ({lat}, {lon}) n'est pas en France"
    if _territory(lon, lat):
        message += (
            " : latitude et longitude semblent inversées (format attendu « lat,lon »)"
        )
    raise SeedConfigError(message)


def validate_radius_km(radius_km: float) -> float:
    if not 0 < radius_km <= MAX_RADIUS_KM:
        raise SeedConfigError(
            f"Rayon invalide ({radius_km} km) : il doit être compris entre 0 et {MAX_RADIUS_KM} km"
        )
    return radius_km


def build_zones(points: list[tuple[float, float]], radius_km: float) -> list[Zone]:
    validate_radius_km(radius_km)
    for lat, lon in points:
        validate_point(lat, lon)
    return [Zone(lat=lat, lon=lon, radius_m=radius_km * 1000) for lat, lon in points]


def check_target_is_local():
    """
    Refuse to write anywhere else than in a local development database.
    """
    host = settings.DATABASES["default"]["HOST"]
    if settings.ENVIRONMENT != "development" or host not in LOCAL_DB_HOSTS:
        raise SeedConfigError(
            "La base cible doit être une base locale de développement "
            f"(DJANGO_ENV={settings.ENVIRONMENT}, POSTGRES_HOST={host})"
        )


# ---------------------------------------------------------------------------
# Extraction queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedTable:
    name: str
    # primary key, whose sequence is reset after the load
    pk: str
    # SQL condition selecting the rows to copy, using the CTEs of selection_ctes()
    where: str
    # column -> SQL expression replacing its value (used to drop personal data)
    overrides: dict


# Tables in loading order: addresses must exist before the buildings, since
# the trigger maintaining the building <> address link table references them.
SEED_TABLES = [
    SeedTable(
        name="batid_department",
        pk="id",
        where="id IN (SELECT id FROM selected_departments)",
        overrides={},
    ),
    SeedTable(
        name="batid_department_subdivided",
        pk="id",
        where=(
            "code IN (SELECT code FROM batid_department "
            "WHERE id IN (SELECT id FROM selected_departments))"
        ),
        overrides={},
    ),
    SeedTable(
        name="batid_city",
        pk="id",
        where="id IN (SELECT id FROM selected_cities)",
        overrides={},
    ),
    SeedTable(
        name="batid_address",
        pk="internal_id",
        where="internal_id IN (SELECT internal_id FROM selected_addresses)",
        overrides={},
    ),
    SeedTable(
        name="batid_building",
        pk="id",
        where="id IN (SELECT id FROM selected_buildings)",
        overrides={
            "event_user_id": "NULL",
            "validated_by": "'{}'::integer[]",
        },
    ),
]

# Tables emptied by the --truncate option, on top of the seeded ones
EXTRA_TRUNCATED_TABLES = [
    "batid_building_history",
    "batid_buildingaddressesinternalidreadonly",
    "batid_buildingvalidatedbyreadonly",
]


def selection_ctes(cursor, zones: list[Zone]) -> str:
    """
    Return the WITH clause selecting the ids of the rows to copy.

    The CTEs are MATERIALIZED so that each spatial join is planned on its own:
    a few zones joined to a big table through its spatial index.
    """
    values = ", ".join(
        cursor.mogrify(
            "(ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)",
            [z.lon, z.lat, z.radius_m, z.radius_deg],
        ).decode()
        for z in zones
    )

    return f"""
        WITH zones(pt, radius_m, radius_deg) AS (VALUES {values}),
        selected_buildings AS MATERIALIZED (
            SELECT DISTINCT b.id
            FROM zones z
            JOIN batid_building b
                ON (ST_DWithin(b.shape, z.pt, z.radius_deg) OR ST_DWithin(b.point, z.pt, z.radius_deg))
                AND ST_DWithin(COALESCE(b.shape, b.point)::geography, z.pt::geography, z.radius_m)
        ),
        selected_addresses AS MATERIALIZED (
            SELECT unnest(b.addresses_internal_id) AS internal_id
            FROM batid_building b
            WHERE b.id IN (SELECT id FROM selected_buildings)
            UNION
            SELECT a.internal_id
            FROM zones z
            JOIN batid_address a
                ON ST_DWithin(a.point, z.pt, z.radius_deg)
                AND ST_DWithin(a.point::geography, z.pt::geography, z.radius_m)
        ),
        selected_cities AS MATERIALIZED (
            SELECT DISTINCT c.id
            FROM zones z
            JOIN batid_city c ON ST_DWithin(c.shape, z.pt, z.radius_deg)
        ),
        selected_departments AS MATERIALIZED (
            SELECT DISTINCT d.id
            FROM zones z
            JOIN batid_department d ON ST_DWithin(d.shape, z.pt, z.radius_deg)
        )
    """


def count_rows(source_conn, zones: list[Zone]) -> dict[str, int]:
    """
    Count, on the source database, the rows each table would receive.
    """
    counts = {}
    with source_conn.cursor() as cursor:
        ctes = selection_ctes(cursor, zones)
        for table in SEED_TABLES:
            cursor.execute(
                f"{ctes} SELECT count(*) FROM {table.name} WHERE {table.where}"
            )
            counts[table.name] = cursor.fetchone()[0]
    return counts


def _table_columns(cursor, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        [table],
    )
    return [row[0] for row in cursor.fetchall()]


def _reset_sequence(cursor, table: str, column: str):
    cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", [table, column])
    sequence = cursor.fetchone()[0]

    if sequence is None:
        # the sequence may be attached through the column DEFAULT only
        cursor.execute(
            """
            SELECT column_default FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            [table, column],
        )
        default = cursor.fetchone()[0] or ""
        match = re.search(r"nextval\('([^']+)'", default)
        if not match:
            return
        sequence = match.group(1)

    cursor.execute(
        f"SELECT setval(%s, COALESCE((SELECT MAX({column}) FROM {table}), 0) + 1, false)",
        [sequence],
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def target_is_empty() -> bool:
    with connection.cursor() as cursor:
        for table in SEED_TABLES:
            cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {table.name})")
            if cursor.fetchone()[0]:
                return False
    return True


def seed(
    source_conn, zones: list[Zone], truncate: bool = False, log=print
) -> dict[str, int]:
    """
    Copy the selected rows from the source connection (psycopg2) into the
    default database. Everything happens in a single transaction.
    Returns the number of rows loaded per table.
    """
    check_target_is_local()

    loaded = {}
    with transaction.atomic():
        with connection.cursor() as target, source_conn.cursor() as source:
            # The app statement_timeout (a few seconds) is far too short for
            # bulk copies, on both sides.
            target.execute("SET LOCAL statement_timeout = 0")
            source.execute("SET statement_timeout = 0")
            # Keep the source sys_period and do not create history rows.
            # Raw SQL rather than building_versioning_dangerously_disabled(),
            # whose cleanup would hide the original error of a failed copy.
            target.execute(f"SET LOCAL {DISABLE_BUILDING_VERSIONING_SETTING} = 'on'")

            if truncate:
                tables = [t.name for t in SEED_TABLES] + EXTRA_TRUNCATED_TABLES
                # CASCADE also empties the local tables referencing those ones (reports, ...)
                target.execute(f"TRUNCATE {', '.join(tables)} CASCADE")

            ctes = selection_ctes(source, zones)

            for table in SEED_TABLES:
                target_columns = _table_columns(target, table.name)
                source_columns = set(_table_columns(source, table.name))
                columns = [c for c in target_columns if c in source_columns]

                missing = [c for c in target_columns if c not in source_columns]
                if missing:
                    log(
                        f"  ⚠ {table.name} : colonnes absentes de la source, "
                        f"laissées à leur valeur par défaut : {', '.join(missing)}"
                    )

                select_list = ", ".join(table.overrides.get(c, c) for c in columns)
                column_list = ", ".join(columns)

                with tempfile.TemporaryFile() as buffer:
                    source.copy_expert(
                        f"COPY ({ctes} SELECT {select_list} FROM {table.name} "
                        f"WHERE {table.where}) TO STDOUT",
                        buffer,
                    )
                    buffer.seek(0)
                    target.copy_expert(
                        f"COPY {table.name} ({column_list}) FROM STDIN", buffer
                    )

                target.execute(f"SELECT count(*) FROM {table.name}")
                loaded[table.name] = target.fetchone()[0]
                log(f"  ✓ {table.name} : {loaded[table.name]} lignes")

                _reset_sequence(target, table.name, table.pk)

    return loaded
