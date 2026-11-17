import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import boto3
import requests
from batid.services.tchap import Code, TchapLevel, notify_tech
from botocore.config import Config  # type: ignore[import-untyped]

# ponytail: fixed floor, prod backups are 71-72 GB; lower it if the database shrinks
BACKUP_MIN_SIZE_BYTES = 50 * 10**9


# main function to be called by the cron job
def backup_to_s3():
    backup_id, backup_name = create_scaleway_db_backup()
    download_url = create_backup_download_url(backup_id)
    size = upload_to_s3(backup_name, download_url)
    if size < BACKUP_MIN_SIZE_BYTES:
        # Raised before remove_older_backups, so that the last valid backups are kept
        raise Exception(
            f"Backup {backup_name} is too small: {size} bytes, minimum {BACKUP_MIN_SIZE_BYTES}"
        )
    remove_older_backups()
    notify_tchap(backup_name=backup_name, size=size)


def notify_tchap(*, backup_name: str, size: int) -> None:

    try:
        notify_tech(
            level=TchapLevel.SUCCESS,
            title="Sauvegarde de la base de prod créée chez OVH",
            details=[("Nom", Code(backup_name)), ("Taille", _format_gb(size))],
        )
    except Exception:
        # A retry would start the whole backup again
        logging.exception("Tchap report of the S3 backup failed")


def _format_gb(size: int) -> str:
    return f"{size / 10**9:.2f}".replace(".", ",") + " Go"


def scaleway_headers():
    SCALEWAY_AUTH_TOKEN = os.environ.get("SCALEWAY_AUTH_TOKEN")
    return {"X-Auth-Token": SCALEWAY_AUTH_TOKEN, "Content-Type": "application/json"}


def upload_to_s3(backup_name, download_url):
    """Stream the Scaleway backup to the OVH bucket and return the stored size in bytes."""
    r = requests.get(download_url, headers=scaleway_headers(), stream=True)
    if r.status_code != 200:
        raise Exception(f"Error {r.status_code} while downloading the scaleway backup")

    S3_BACKUP_ACCESS_KEY_ID = os.environ.get("S3_BACKUP_ACCESS_KEY_ID")
    S3_BACKUP_SECRET_ACCESS_KEY = os.environ.get("S3_BACKUP_SECRET_ACCESS_KEY")
    S3_BACKUP_ENDPOINT_URL = os.environ.get("S3_BACKUP_ENDPOINT_URL")
    S3_BACKUP_REGION_NAME = os.environ.get("S3_BACKUP_REGION_NAME")
    S3_BACKUP_BUCKET_NAME = os.environ.get("S3_BACKUP_BUCKET_NAME")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=S3_BACKUP_ACCESS_KEY_ID,
        aws_secret_access_key=S3_BACKUP_SECRET_ACCESS_KEY,
        endpoint_url=S3_BACKUP_ENDPOINT_URL,
        region_name=S3_BACKUP_REGION_NAME,
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )

    # OVH S3's maximum number of parts for multipart upload is 10000
    # Chunk size by default is 8Mo
    chunk_size = 64 * 1024 * 1024  # 64Mo
    transfer_config = boto3.s3.transfer.TransferConfig(
        multipart_threshold=chunk_size,
        multipart_chunksize=chunk_size,
        max_concurrency=4,
        use_threads=True,
    )

    s3.upload_fileobj(r.raw, S3_BACKUP_BUCKET_NAME, backup_name, Config=transfer_config)

    object_exists = s3.get_waiter("object_exists")
    object_exists.wait(Bucket=S3_BACKUP_BUCKET_NAME, Key=backup_name)

    return s3.head_object(Bucket=S3_BACKUP_BUCKET_NAME, Key=backup_name)[
        "ContentLength"
    ]


def create_scaleway_db_backup():
    SCALEWAY_DB_NAME = os.environ.get("SCALEWAY_DB_NAME")
    SCALEWAY_INSTANCE_ID = os.environ.get("SCALEWAY_INSTANCE_ID")
    SCALEWAY_REGION = os.environ.get("SCALEWAY_REGION")

    backup_name = f"rnb_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

    # RFC 3339 formatted datetime in a week
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    data = {
        "database_name": SCALEWAY_DB_NAME,
        "instance_id": SCALEWAY_INSTANCE_ID,
        "name": backup_name,
        "expires_at": expires_at,
    }

    # create a scaleway backup
    r = requests.post(
        f"https://api.scaleway.com/rdb/v1/regions/{SCALEWAY_REGION}/backups",
        data=json.dumps(data),
        headers=scaleway_headers(),
    )

    if r.status_code != 200:
        raise Exception("Error while creating the scaleway backup")
    else:
        res = r.json()
        return (res["id"], res["name"])


def create_backup_download_url(backup_id):
    wait_until_backup_is_ready(backup_id)
    create_download_url(backup_id)
    download_url = wait_for_download_url(backup_id)
    return download_url


def wait_until_backup_is_ready(backup_id):
    print("Waiting for the backup to be ready")
    time.sleep(10)
    tries = 0
    while True:
        # stop trying after 5 hours
        if tries > 6 * 5:
            raise Exception("Timeout while creating the scaleway backup")
        if is_backup_ready(backup_id):
            break
        tries += 1
        # sleep 10 minutes
        time.sleep(10 * 60)
    return True


def create_download_url(backup_id):
    print("Creating the download url")
    SCALEWAY_REGION = os.environ.get("SCALEWAY_REGION")
    r = requests.post(
        f"https://api.scaleway.com/rdb/v1/regions/{SCALEWAY_REGION}/backups/{backup_id}/export",
        headers=scaleway_headers(),
    )

    if r.status_code != 200:
        raise Exception("Error while creating the scaleway backup download url")
    return True


def wait_for_download_url(backup_id):
    print("Waiting for the download url")
    tries = 0
    time.sleep(10)
    download_url = None

    while True:
        # stop trying after 1 hour
        if tries > 30:
            raise Exception("Timeout while creating the scaleway backup download url")
        download_url = backup_download_url(backup_id)
        if download_url is not None:
            break
        tries += 1

        # sleep 2 minutes
        time.sleep(2 * 60)

    return download_url


def is_backup_ready(backup_id):
    SCALEWAY_REGION = os.environ.get("SCALEWAY_REGION")
    r = requests.get(
        f"https://api.scaleway.com/rdb/v1/regions/{SCALEWAY_REGION}/backups/{backup_id}",
        headers=scaleway_headers(),
    )

    if r.status_code != 200:
        raise Exception(f"Error while getting the scaleway backup {backup_id}")
    else:
        return r.json()["status"] == "ready"


def backup_download_url(backup_id):
    SCALEWAY_REGION = os.environ.get("SCALEWAY_REGION")
    r = requests.get(
        f"https://api.scaleway.com/rdb/v1/regions/{SCALEWAY_REGION}/backups/{backup_id}",
        headers=scaleway_headers(),
    )

    if r.status_code != 200:
        raise Exception(f"Error while getting the scaleway backup {backup_id}")
    else:
        return r.json()["download_url"]


def remove_older_backups():
    S3_BACKUP_ACCESS_KEY_ID = os.environ.get("S3_BACKUP_ACCESS_KEY_ID")
    S3_BACKUP_SECRET_ACCESS_KEY = os.environ.get("S3_BACKUP_SECRET_ACCESS_KEY")
    S3_BACKUP_ENDPOINT_URL = os.environ.get("S3_BACKUP_ENDPOINT_URL")
    S3_BACKUP_REGION_NAME = os.environ.get("S3_BACKUP_REGION_NAME")
    S3_BACKUP_BUCKET_NAME = os.environ.get("S3_BACKUP_BUCKET_NAME")

    s3_resource = boto3.resource(
        "s3",
        aws_access_key_id=S3_BACKUP_ACCESS_KEY_ID,
        aws_secret_access_key=S3_BACKUP_SECRET_ACCESS_KEY,
        endpoint_url=S3_BACKUP_ENDPOINT_URL,
        region_name=S3_BACKUP_REGION_NAME,
    )

    bucket = s3_resource.Bucket(S3_BACKUP_BUCKET_NAME)
    now = datetime.now(timezone.utc)
    one_month_ago = now - timedelta(days=30)

    for obj in bucket.objects.all():
        if obj.last_modified < one_month_ago:
            logging.info(f"S3 external backup, deleting older backup {obj.key}")
            obj.delete()
