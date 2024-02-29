from turtle import down
import boto3
import json
from datetime import datetime, timedelta, timezone
import os
import requests
import time


# main function to be called by the cron job
def backup_to_s3(task_id=None):
    try:
        (backup_id, backup_name) = create_scaleway_db_backup()
        download_url = create_backup_download_url(backup_id)
        upload_to_s3(backup_name, download_url)
        notify_mattermost(backup_name)
    except Exception as e:
        notify_mattermost_error(e, task_id)
        raise e


def notify_mattermost_error(error, task_id):
    MATTERMOST_RNB_TECH_WEBHOOK_URL = os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL")

    data = {
        "username": "backup-bot",
        "text": f"Une erreur est survenue lors de la création d'un backup de la base de production du RNB : {error}. Task ID : {task_id}",
    }

    r = requests.post(MATTERMOST_RNB_TECH_WEBHOOK_URL, data=json.dumps(data))

    if r.status_code != 200:
        raise Exception("Error while sending the mattermost notification")


def notify_mattermost(backup_name):
    MATTERMOST_RNB_TECH_WEBHOOK_URL = os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL")

    data = {
        "username": "backup-bot",
        "text": f"Un nouveau backup de la base de production du RNB a été créé chez OVH : {backup_name}.",
    }

    r = requests.post(MATTERMOST_RNB_TECH_WEBHOOK_URL, data=json.dumps(data))

    if r.status_code != 200:
        raise Exception("Error while sending the mattermost notification")


def scaleway_headers():
    SCALEWAY_AUTH_TOKEN = os.environ.get("SCALEWAY_AUTH_TOKEN")
    return {"X-Auth-Token": SCALEWAY_AUTH_TOKEN, "Content-Type": "application/json"}


def upload_to_s3(backup_name, download_url):
    r = requests.get(download_url, headers=scaleway_headers(), stream=True)

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
    )

    s3.upload_fileobj(r.raw, S3_BACKUP_BUCKET_NAME, backup_name)

    object_exists = s3.get_waiter("object_exists")
    object_exists.wait(Bucket=S3_BACKUP_BUCKET_NAME, Key=backup_name)


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
