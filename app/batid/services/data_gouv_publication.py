import glob
import hashlib
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from typing import IO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import boto3
import requests
from batid.services.administrative_areas import dpts_list
from celery import Signature
from django.conf import settings
from django.db import connection, transaction

from app.settings import WRITABLE_DATA_DIR


def datagouv_publication_enabled() -> bool:
    return os.environ.get("ENABLE_DATAGOUV_PUBLICATION") == "true"


def publish(*, area: str, run_id: str | None = None) -> bool:
    """Build the area archive and send it to data.gouv.fr. Return False when the
    publication is disabled: the archive is built, nothing is sent.

    A department of a run keeps its archive in the run directory, where the national
    file is assembled from it; the national file then removes that directory."""
    print(f"Processing area: {area}")

    if area == "nat":
        return publish_national(run_id=run_id)

    if run_id:
        archive = build_department_archive(dept=area, run_dir=run_directory(run_id))
        return send_archive(area=area, archive=archive)

    directory_name = create_directory(area)
    try:
        archive = create_archive(directory_name, area)
        return send_archive(area=area, archive=archive)
    finally:
        # we always cleanup the directory, no matter what happens
        cleanup_directory(directory_name)


def publish_national(*, run_id: str | None) -> bool:
    # Without a run (manual launch), every department archive is missing: the
    # national file builds them all in a private run directory.
    run_id = run_id or uuid4().hex
    try:
        directory_name = create_directory("nat")
        try:
            archive = create_national_archive(directory=directory_name, run_id=run_id)
            return send_archive(area="nat", archive=archive)
        finally:
            cleanup_directory(directory_name)
    finally:
        # Missing when no department archive was built.
        if os.path.isdir(run_directory(run_id)):
            cleanup_directory(run_directory(run_id))


def send_archive(*, area: str, archive: tuple[str, int, str]) -> bool:
    archive_path, archive_size, archive_sha1 = archive
    enabled = datagouv_publication_enabled()
    if enabled:
        public_url = upload_to_s3(archive_path)
        publish_on_data_gouv_with_retries(
            area=area,
            public_url=public_url,
            archive_size=archive_size,
            archive_sha1=archive_sha1,
        )
    return enabled


RUN_DIRECTORY_PREFIX = "datagouvfr_run_"
# Each department archive moved in updates the directory mtime, and one department
# export takes far less than this.
RUN_DIRECTORY_MAX_IDLE_S = 24 * 3600


def run_directory(run_id: str) -> str:
    return os.path.join(WRITABLE_DATA_DIR, f"{RUN_DIRECTORY_PREFIX}{run_id}")


def remove_previous_run_directories() -> None:
    """Remove the run directories (about 12 GB each) left by chains stopped before
    their national file. A manual national can still be filling its own for about
    9 h, hence the idle delay."""
    for path in glob.glob(os.path.join(WRITABLE_DATA_DIR, f"{RUN_DIRECTORY_PREFIX}*")):
        if time.time() - os.path.getmtime(path) > RUN_DIRECTORY_MAX_IDLE_S:
            cleanup_directory(path)


def department_archive_path(*, run_dir: str, dept: str) -> str:
    return os.path.join(run_dir, f"RNB_{dept}.csv.zip")


def build_department_archive(*, dept: str, run_dir: str) -> tuple[str, int, str]:
    """Build the department archive and move it into the run directory.

    The move comes after the export succeeded: a zip closed on a failed COPY is still
    a valid, truncated archive, so a file of the run directory is always complete."""
    directory_name = create_directory(dept)
    try:
        archive_path, archive_size, archive_sha1 = create_archive(directory_name, dept)
        os.makedirs(run_dir, exist_ok=True)
        kept_path = department_archive_path(run_dir=run_dir, dept=dept)
        os.replace(archive_path, kept_path)
    finally:
        cleanup_directory(directory_name)
    return kept_path, archive_size, archive_sha1


def create_directory(area):
    # mkdtemp: two runs of an area started within the same second (a manual national
    # next to the chain's one) get their own directory, each removed by its own run.
    return tempfile.mkdtemp(
        prefix=f'datagouvfr_publication_{area}_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}_',
        dir=WRITABLE_DATA_DIR,
    )


# Return the global path of a file WITHOUT the extension
def file_path(directory_name, code_area):
    return directory_name + "/RNB_" + str(code_area)


def sql_query(code_area):
    # The department's buildings are read once, through the spatial index.
    # MATERIALIZED: the planner overestimates this join about 20 times; without
    # the fence it walks the 45M buildings in id order to deduplicate them, or
    # reads every building a second time by id. DISTINCT ON: a point lying on
    # the edge of two subdivided polygons of the department must give one row.
    area_cte = f"""WITH area_bdg AS MATERIALIZED (
        SELECT area_bdg.*
        FROM batid_department_subdivided dpt
        JOIN batid_building area_bdg ON ST_Intersects(dpt.shape, area_bdg.point)
        WHERE dpt.code = '{code_area}' AND area_bdg.is_active
    )"""
    return export_sql(
        area_cte=area_cte,
        area_from="(SELECT DISTINCT ON (id) * FROM area_bdg) AS bdg",
        header=True,
    )


def export_sql(*, area_cte: str, area_from: str, header: bool) -> str:
    # Addresses are aggregated per building in a subquery, not with a join and a
    # GROUP BY: the join let the planner hash the buildings on their address id,
    # and the buildings without address (NULL key) all fall in one hash batch that
    # can never be split. Postgres then kept doubling the batches until the
    # database was killed out of memory (2026-11-14, department 13).
    sql = f"""
    COPY (
        {area_cte}
        select bdg.rnb_id as rnb_id,
        ST_AsEWKT(bdg.point) as point,
        ST_AsEWKT(bdg.shape) as shape,
        bdg.status as status,
        bdg.ext_ids as ext_ids,
        (
           SELECT coalesce(json_agg(
               json_build_object(
                   'cle_interop_ban', addr.cle_interop,
                   'street_number', addr.street_number,
                   'street_rep', addr.street_rep,
                   'street', addr.street,
                   'city_zipcode', addr.city_zipcode,
                   'city_name', addr.city_name
               ) ORDER BY addr.cle_interop
           ), '[]'::json)
           FROM batid_buildingaddressesinternalidreadonly bdg_addr
           JOIN batid_address addr ON addr.internal_id = bdg_addr.address_id
           WHERE bdg_addr.building_id = bdg.id AND addr.cle_interop IS NOT NULL
       ) AS addresses,
        (
           SELECT json_agg(json_build_object('id', p.id, 'bdg_cover_ratio',
               CASE
                   WHEN ST_GeometryType(bdg.shape) = 'ST_Point' THEN 1.0
                   WHEN ST_GeometryType(bdg.shape) IN ('ST_Polygon', 'ST_MultiPolygon') THEN
                       CASE
                           WHEN ST_Area(bdg.shape) > 0 THEN
                               ST_Area(ST_Intersection(bdg.shape, p.shape)) / ST_Area(bdg.shape)
                           ELSE 0.0
                       END
                   ELSE 0.0
               END
           ))
           FROM batid_plot p
           WHERE ST_Intersects(p.shape, bdg.shape)
       ) AS plots,
        (
           SELECT coalesce(json_agg(
               json_build_object(
                   'id', u.id,
                   'username', u.username,
                   'organization_name', org.name,
                   'organization_short_name', org.short_name
               ) ORDER BY u.id
           ), '[]'::json)
           FROM batid_buildingvalidatedbyreadonly v
           JOIN auth_user u ON u.id = v.user_id
           LEFT JOIN batid_userprofile up ON up.user_id = u.id
           LEFT JOIN batid_organization org ON org.id = up.organization_id
           WHERE v.building_id = bdg.id
       ) AS validated_by
        FROM {area_from}
        WHERE bdg.is_active
    )  TO STDOUT WITH CSV {"HEADER " if header else ""}DELIMITER ';'
    """

    return sql


def sha1sum(filename):
    h = hashlib.sha1()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()


def create_archive(directory_name, code_area):
    archive_path = f"{file_path(directory_name, code_area)}.csv.zip"
    sql = sql_query(code_area)

    # Stream the COPY output straight into the zip entry: no intermediate CSV on disk.
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        with open_zip_entry(
            archive=archive, entry_name=f"RNB_{code_area}.csv"
        ) as entry:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    set_statement_timeout(cursor)
                    with cursor.copy(sql) as copy:
                        for data in copy:
                            entry.write(data)

    return archive_summary(archive_path)


def open_zip_entry(*, archive: ZipFile, entry_name: str) -> IO[bytes]:
    # force_zip64: the entry size is unknown upfront and exceeds 4 GB for the national export.
    # Explicit ZipInfo: opening by name would date the entry 1980-01-01; a ZipInfo defaults to ZIP_STORED.
    # external_attr: without it the entry would be written with mode 0o600 and extract as rw-------.
    entry_info = ZipInfo(entry_name, date_time=datetime.now().timetuple()[:6])
    entry_info.compress_type = ZIP_DEFLATED
    entry_info.external_attr = 0o100644 << 16
    return archive.open(entry_info, "w", force_zip64=True)


def set_statement_timeout(cursor) -> None:
    cursor.execute(
        "SET statement_timeout = %(statement_timeout)s;",
        {"statement_timeout": settings.DATA_GOUV_POSTGRES_STATEMENT_TIMEOUT},
    )


def archive_summary(archive_path: str) -> tuple[str, int, str]:
    archive_size = os.path.getsize(archive_path)

    archive_sha1 = sha1sum(archive_path)
    logging.info(
        f"zip archive for data.gouv.fr created: {archive_path} ({archive_size} bytes, sha1: {archive_sha1})"
    )
    return (archive_path, archive_size, archive_sha1)


# A building edited less than this before the oldest department export is exported
# fresh by the national file. It covers a department export (its COPY snapshot is
# taken before the archive mtime) and an edit transaction open across a department
# snapshot (lower(sys_period) is the start of the edit transaction).
NATIONAL_FRESH_MARGIN = timedelta(hours=24)

NATIONAL_WRITE_BATCH_BYTES = 1024 * 1024

# Buildings that cannot be taken from the department files: outside every
# department or on a department border (in zero or two files), or edited since the
# department files were written (stale or deactivated there). The per-building
# subquery counts each building once, whatever the number of subdivided polygons.
NATIONAL_FRESH_SQL = """
CREATE TEMP TABLE national_fresh ON COMMIT DROP AS
SELECT bdg.id, bdg.rnb_id, bdg.is_active
FROM batid_building bdg
WHERE bdg.is_active
AND (
    SELECT count(DISTINCT dpt.code)
    FROM batid_department_subdivided dpt
    WHERE ST_Intersects(dpt.shape, bdg.point)
) <> 1
UNION
SELECT bdg.id, bdg.rnb_id, bdg.is_active
FROM batid_building bdg
WHERE lower(bdg.sys_period) >= %(since)s
"""


class NationalArchiveError(Exception):
    """The national file cannot be assembled from the department archives."""


def create_national_archive(*, directory: str, run_id: str) -> tuple[str, int, str]:
    """Assemble the national archive from the department archives of the run.

    Each active building appears once: one that is active in the snapshot and not
    in national_fresh has one department and a version older than `since`, so it is
    in that department file once and in no other; every other building comes only
    from the fresh export, and only if active. The row count check refuses the file
    when this does not hold (an edit transaction open longer than
    NATIONAL_FRESH_MARGIN across a department export)."""
    department_archives = department_archives_of_run(run_directory(run_id))

    oldest_export = min(os.path.getmtime(path) for path in department_archives)
    since = (
        datetime.fromtimestamp(oldest_export, tz=timezone.utc) - NATIONAL_FRESH_MARGIN
    )
    header = csv_header(department_archives[0])

    archive_path = f"{file_path(directory, 'nat')}.csv.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        with open_zip_entry(archive=archive, entry_name="RNB_nat.csv") as entry:
            entry.write(header)
            active_count, fresh_count, skip_ids = write_fresh_buildings(
                entry=entry, since=since
            )

            started = time.monotonic()
            department_count = sum(
                copy_department_records(
                    archive_path=path, entry=entry, header=header, skip_ids=skip_ids
                )
                for path in department_archives
            )
            logging.info(
                f"national file: {department_count} department rows copied in {time.monotonic() - started:.0f} s"
            )

    if department_count + fresh_count != active_count:
        raise NationalArchiveError(
            f"National row count mismatch: {department_count} department rows + "
            f"{fresh_count} fresh rows, {active_count} active buildings"
        )
    return archive_summary(archive_path)


def department_archives_of_run(run_dir: str) -> list[str]:
    """Paths of the department archives of the run, in dpts_list() order. A missing
    one (failed department task, manual national launch) is built here."""
    started = time.monotonic()
    paths = []
    for dept in dpts_list():
        path = department_archive_path(run_dir=run_dir, dept=dept)
        if not os.path.exists(path):
            try:
                build_department_archive(dept=dept, run_dir=run_dir)
            except Exception as e:
                raise NationalArchiveError(
                    f"Department {dept} archive could not be built for the national file: {e}"
                ) from e
        paths.append(path)
    logging.info(
        f"national file: department archives ready in {time.monotonic() - started:.0f} s"
    )
    return paths


def write_fresh_buildings(
    *, entry: IO[bytes], since: datetime
) -> tuple[int, int, set[bytes]]:
    """Write the buildings that cannot come from the department files. Return the
    active building count, the number of rows written and the rnb_ids to drop from
    the department files, all read from one snapshot."""
    started = time.monotonic()
    with transaction.atomic():
        with connection.cursor() as cursor:
            # Postgres only accepts it before the first query of the transaction.
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            set_statement_timeout(cursor)
            cursor.execute("SELECT count(*) FROM batid_building WHERE is_active")
            (active_count,) = cursor.fetchone()
            cursor.execute(NATIONAL_FRESH_SQL, {"since": since})
            cursor.execute("SELECT rnb_id, is_active FROM national_fresh")
            skip_ids = set()
            fresh_count = 0
            for rnb_id, is_active in cursor:
                skip_ids.add(rnb_id.encode())
                if is_active:
                    fresh_count += 1
            logging.info(
                f"national file: {len(skip_ids)} buildings to export fresh, found in {time.monotonic() - started:.0f} s"
            )

            started = time.monotonic()
            sql = export_sql(
                area_cte="",
                area_from="batid_building bdg JOIN national_fresh ON national_fresh.id = bdg.id",
                header=False,
            )
            with cursor.copy(sql) as copy:
                for data in copy:
                    entry.write(data)
    logging.info(
        f"national file: {fresh_count} fresh rows exported in {time.monotonic() - started:.0f} s"
    )
    return active_count, fresh_count, skip_ids


def csv_header(archive_path: str) -> bytes:
    with ZipFile(archive_path) as archive:
        (entry_name,) = archive.namelist()
        with archive.open(entry_name) as entry:
            return next(csv_records(entry))


def copy_department_records(
    *, archive_path: str, entry: IO[bytes], header: bytes, skip_ids: set[bytes]
) -> int:
    """Copy the records of a department archive into the national entry, byte for
    byte, without its header and without the skipped buildings. Return the number
    of records written."""
    written = 0
    batch: list[bytes] = []
    batch_size = 0
    with ZipFile(archive_path) as archive:
        (entry_name,) = archive.namelist()
        with archive.open(entry_name) as department_entry:
            records = csv_records(department_entry)
            if next(records, None) != header:
                raise NationalArchiveError(
                    f"{entry_name} header differs from the other department files"
                )
            for record in records:
                # rnb_id is the first field, never quoted
                if record.partition(b";")[0] in skip_ids:
                    continue
                batch.append(record)
                batch_size += len(record)
                written += 1
                if batch_size >= NATIONAL_WRITE_BATCH_BYTES:
                    entry.write(b"".join(batch))
                    batch = []
                    batch_size = 0
    entry.write(b"".join(batch))
    return written


def csv_records(lines: Iterable[bytes]) -> Iterator[bytes]:
    """Yield the raw records of a Postgres CSV export, end of line included.

    Postgres quotes any field holding a newline and doubles the quotes inside it, so
    a record ends at the first end of line after an even number of quotes."""
    parts: list[bytes] = []
    quotes = 0
    for line in lines:
        quotes += line.count(b'"')
        if quotes % 2:
            parts.append(line)
            continue
        if parts:
            parts.append(line)
            line = b"".join(parts)
            parts = []
        quotes = 0
        if not line.endswith(b"\n"):
            raise NationalArchiveError("CSV export truncated in the middle of a record")
        yield line
    if parts:
        raise NationalArchiveError("CSV export truncated in the middle of a record")


def upload_to_s3(archive_path):
    # upload the archive to the Scaleway S3 bucket

    S3_SCALEWAY_ACCESS_KEY_ID = os.environ.get("S3_SCALEWAY_ACCESS_KEY_ID")
    S3_SCALEWAY_SECRET_ACCESS_KEY = os.environ.get("S3_SCALEWAY_SECRET_ACCESS_KEY")
    S3_SCALEWAY_ENDPOINT_URL = os.environ.get("S3_SCALEWAY_ENDPOINT_URL")
    S3_SCALEWAY_REGION_NAME = os.environ.get("S3_SCALEWAY_REGION_NAME")
    S3_SCALEWAY_BUCKET_NAME = os.environ.get("S3_SCALEWAY_BUCKET_NAME")
    S3_SCALEWAY_OPENDATA_DIRECTORY = os.environ.get("S3_SCALEWAY_OPENDATA_DIRECTORY")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=S3_SCALEWAY_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SCALEWAY_SECRET_ACCESS_KEY,
        endpoint_url=S3_SCALEWAY_ENDPOINT_URL,
        region_name=S3_SCALEWAY_REGION_NAME,
    )
    # extract file name from archive path
    archive_name = os.path.basename(archive_path)
    path_on_bucket = f"{S3_SCALEWAY_OPENDATA_DIRECTORY}/{archive_name}"

    # Scaleway S3's maximum number of parts for multipart upload
    MAX_PARTS = 1000
    # compute the corresponding part size
    archive_size = os.path.getsize(archive_path)
    part_size = max(1, int(archive_size * 1.2 / MAX_PARTS))
    config = boto3.s3.transfer.TransferConfig(multipart_chunksize=part_size)

    s3.upload_file(
        archive_path,
        S3_SCALEWAY_BUCKET_NAME,
        path_on_bucket,
        ExtraArgs={"ACL": "public-read"},
        Config=config,
    )

    object_exists = s3.get_waiter("object_exists")
    object_exists.wait(Bucket=S3_SCALEWAY_BUCKET_NAME, Key=path_on_bucket)

    public_url = f"https://{S3_SCALEWAY_BUCKET_NAME}.s3.{S3_SCALEWAY_REGION_NAME}.scw.cloud/{path_on_bucket}"

    return public_url


DATA_GOUV_TIMEOUT_S = 30

# Waits between the 5 attempts: 1, 2, 4 then 8 minutes (15 minutes covered).
DATA_GOUV_RETRY_DELAYS_S = (60, 120, 240, 480)


class DataGouvAccessDenied(Exception):
    """401 or 403 from data.gouv.fr: the key is refused for the whole dataset, every other area would fail the same way."""


class DataGouvUnavailable(Exception):
    """429 or 5xx from data.gouv.fr: the platform is overloaded or down, a later attempt can succeed."""


# Transient errors only: an invalid URL or header (missing DATA_GOUV_BASE_URL for
# instance) or a 4xx answer fails the same way on every attempt and is raised at once.
# TooManyRedirects: data.gouv.fr answered with a redirect loop during its outage of
# 2026-11-14.
DATA_GOUV_RETRYABLE_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.TooManyRedirects,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
    requests.exceptions.JSONDecodeError,
    DataGouvUnavailable,
)


def data_gouv_error(*, message: str, response: requests.Response) -> Exception:
    error = f"{message}: HTTP {response.status_code} {response.text[:200]}"
    if response.status_code in (401, 403):
        return DataGouvAccessDenied(error)
    if response.status_code == 429 or response.status_code >= 500:
        return DataGouvUnavailable(error)
    return Exception(error)


def publish_on_data_gouv_with_retries(*, area, public_url, archive_size, archive_sha1):
    """
    Publish on data.gouv.fr, retrying on transient errors (network errors, timeouts,
    redirect loops, cut or non-JSON bodies, 429 and 5xx answers).
    Replayable: each attempt starts with a GET, so a resource created by a previous
    attempt is updated, not created twice. Other errors (4xx answers, invalid URL)
    are raised at once.
    """
    for delay in DATA_GOUV_RETRY_DELAYS_S:
        try:
            return publish_on_data_gouv(area, public_url, archive_size, archive_sha1)
        except DATA_GOUV_RETRYABLE_ERRORS as e:
            logging.warning(
                f"data.gouv.fr publication failed for area {area}, retrying in {delay} s: {e}"
            )
            time.sleep(delay)
    return publish_on_data_gouv(area, public_url, archive_size, archive_sha1)


def publish_on_data_gouv(area, public_url, archive_size, archive_sha1, format="zip"):
    # publish the archive on data.gouv.fr
    dataset_id = os.environ.get("DATA_GOUV_DATASET_ID")
    resource_id = data_gouv_resource_id(dataset_id, area)

    if area == "nat":
        title = "Export National"
        description = (
            "Export du RNB au format csv pour l’ensemble du territoire français."
        )
    else:
        title = f"Export Départemental {area}"
        description = f"Export du RNB au format csv pour le département {area}."

    # ressource already exists
    if resource_id is not None:
        update_resource_metadata(
            dataset_id,
            resource_id,
            title,
            description,
            public_url,
            archive_size,
            archive_sha1,
            format,
        )
    # ressource don't exist
    else:
        data_gouv_create_resource(
            dataset_id,
            title,
            description,
            public_url,
            archive_size,
            archive_sha1,
            format,
        )

    return True


def data_gouv_create_resource(
    dataset_id, title, description, public_url, archive_size, archive_sha1, format="zip"
):
    DATA_GOUV_BASE_URL = os.environ.get("DATA_GOUV_BASE_URL")
    dataset_url = f"{DATA_GOUV_BASE_URL}/api/1/datasets/{dataset_id}/resources/"
    headers = {
        "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
        "Content-Type": "application/json",
    }

    response = requests.post(
        dataset_url,
        headers=headers,
        json={
            "title": title,
            "description": description,
            "type": "main",
            "url": public_url,
            "filetype": "remote",
            "format": format,
            "filesize": archive_size,
            "checksum": {"type": "sha1", "value": archive_sha1},
            "created_at": str(datetime.now()),
        },
        timeout=DATA_GOUV_TIMEOUT_S,
    )

    if response.status_code != 201:
        raise data_gouv_error(
            message="Error while creating the resource", response=response
        )

    return True


def data_gouv_resource_id(dataset_id, area):
    # get the resource id from data.gouv.fr
    DATA_GOUV_BASE_URL = os.environ.get("DATA_GOUV_BASE_URL")
    dataset_url = f"{DATA_GOUV_BASE_URL}/api/1/datasets/{dataset_id}/"

    response = requests.get(dataset_url, timeout=DATA_GOUV_TIMEOUT_S)

    if response.status_code != 200:
        raise data_gouv_error(
            message="Error while fetching the dataset", response=response
        )
    else:
        res = response.json()
        resources = res["resources"]
        for resource in resources:
            if resource["format"] == "zip" and (
                (area == "nat" and resource["title"] == "Export National")
                or (
                    area != "nat"
                    and resource["title"] == f"Export Départemental {area}"
                )
            ):
                return resource["id"]
        return None


def update_resource_metadata(
    dataset_id,
    resource_id,
    title,
    description,
    public_url,
    archive_size,
    archive_sha1,
    format=zip,
):
    # update the resource url on data.gouv.fr
    DATA_GOUV_BASE_URL = os.environ.get("DATA_GOUV_BASE_URL")
    update_url = (
        f"{DATA_GOUV_BASE_URL}/api/1/datasets/{dataset_id}/resources/{resource_id}/"
    )
    headers = {
        "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
        "Content-Type": "application/json",
    }

    print(f"Updating resource {resource_id} in dataset {dataset_id}")
    print(f"Update URL: {update_url}")

    response = requests.put(
        update_url,
        headers=headers,
        json={
            "title": title,
            "description": description,
            "type": "main",
            "url": public_url,
            "filetype": "remote",
            "format": format,
            "filesize": archive_size,
            "checksum": {"type": "sha1", "value": archive_sha1},
            "extras": {
                # This "analysis:last-modified-at" key is not documented in the data.gouv.fr API documentation
                # but we can see here : https://github.com/opendatateam/udata/blob/13810fa64b76b316cd84dc2cc7dff7c3e7d6df4b/udata/core/dataset/models.py#L373
                # that we can use it to update the last modification date of the resource if it is a "remote" file
                "analysis:last-modified-at": str(datetime.now())
            },
        },
        timeout=DATA_GOUV_TIMEOUT_S,
    )

    if response.status_code != 200:
        raise data_gouv_error(
            message="Error while updating the resource url", response=response
        )
    else:
        return True


def cleanup_directory(directory_name):
    """Remove a working directory once its area is sent or has failed. A removal
    error must not replace that outcome (a published file reported as failed, an
    export error hidden): it is logged, hence sent to Sentry."""
    try:
        shutil.rmtree(directory_name)
    except OSError:
        logging.exception(f"data.gouv.fr directory not removed: {directory_name}")


def get_area_publish_task(area: str, *, run_id: str | None = None):

    kwargs = {"run_id": run_id} if run_id else None

    if area == "nat":
        return Signature(
            "batid.tasks.publish_datagouv_national", kwargs=kwargs, immutable=True
        )

    if area in dpts_list():
        return Signature(
            "batid.tasks.publish_datagouv_dpt", args=[area], kwargs=kwargs, immutable=True  # type: ignore[arg-type]
        )

    raise ValueError(
        f"Unknown area: {area}. It must be either 'nat' or a department code. '{area}' given."
    )
