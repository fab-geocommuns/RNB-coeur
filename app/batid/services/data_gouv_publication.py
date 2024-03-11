import re
from wsgiref import headers
from django.db import connection
from datetime import datetime
import os
from zipfile import ZipFile, ZIP_DEFLATED
import boto3
import requests
import hashlib
import shutil
import logging


def publish():
    # Publish the RNB on data.gouv.fr
    directory_name = create_directory()

    try:
        create_rnb_csv_files(directory_name)
        (archive_path, archive_size, archive_sha1) = create_archive(directory_name)
        public_url = upload_to_s3(archive_path)
        publish_on_data_gouv(public_url, archive_size, archive_sha1)
        return True
    except Exception as e:
        logging.error(f"Error while publishing the RNB on data.gouv.fr: {e}")
        return False
    finally:
        # we always cleanup the directory, no matter what happens
        cleanup_directory(directory_name)


def create_directory():
    directory_name = (
        f'datagouvfr_publication_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    )
    os.mkdir(directory_name)
    return directory_name


def create_rnb_csv_files(directory_name):
    create_building_csv(directory_name)
    create_building_address_csv(directory_name)
    create_address_csv(directory_name)

    return True


def create_building_csv(directory_name):
    with connection.cursor() as cursor:
        sql = """
            COPY (
                select "id","rnb_id",ST_AsText("point") as point,"created_at","updated_at",ST_AsText("shape") as shape,"ext_ids" from batid_building
            ) TO STDOUT WITH CSV HEADER
        """

        with open(f"{directory_name}/rnb_building.csv", "w") as fp:
            cursor.copy_expert(sql, fp)


def create_building_address_csv(directory_name):
    with connection.cursor() as cursor:
        sql = """
            COPY (
                select "building_id", "address_id" from batid_building_addresses bba
            ) TO STDOUT WITH CSV HEADER
        """

        with open(f"{directory_name}/rnb_building_address.csv", "w") as fp:
            cursor.copy_expert(sql, fp)


def create_address_csv(directory_name):
    with connection.cursor() as cursor:
        sql = """
            COPY (
                select "id","source","street_number","street_rep","street_name","street_type","city_name","city_zipcode","created_at","updated_at","point","city_insee_code" from batid_address ba
            ) TO STDOUT WITH CSV HEADER
        """

        with open(f"{directory_name}/rnb_address.csv", "w") as fp:
            cursor.copy_expert(sql, fp)


def sha1sum(filename):
    h = hashlib.sha1()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()


def create_archive(directory_name):
    files = os.listdir(directory_name)
    archive_path = f"{directory_name}/RNB_{directory_name}.zip"

    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zip:
        for file in files:
            zip.write(f"{directory_name}/{file}")

    archive_size = os.path.getsize(archive_path)

    archive_sha1 = sha1sum(archive_path)
    logging.info(
        f"zip archive for data.gouv.fr created: {archive_path} ({archive_size} bytes, sha1: {archive_sha1})"
    )
    return (archive_path, archive_size, archive_sha1)


def upload_to_s3(archive_path):
    # upload the archive to the Scaleway S3 bucket

    S3_SCALEWAY_ACCESS_KEY_ID = os.environ.get("S3_SCALEWAY_ACCESS_KEY_ID")
    S3_SCALEWAY_SECRET_ACCESS_KEY = os.environ.get("S3_SCALEWAY_SECRET_ACCESS_KEY")
    S3_SCALEWAY_ENDPOINT_URL = os.environ.get("S3_SCALEWAY_ENDPOINT_URL")
    S3_SCALEWAY_REGION_NAME = os.environ.get("S3_SCALEWAY_REGION_NAME")
    S3_SCALEWAY_BUCKET_NAME = os.environ.get("S3_SCALEWAY_BUCKET_NAME")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=S3_SCALEWAY_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SCALEWAY_SECRET_ACCESS_KEY,
        endpoint_url=S3_SCALEWAY_ENDPOINT_URL,
        region_name=S3_SCALEWAY_REGION_NAME,
    )
    # extract file name from archive path
    archive_name = os.path.basename(archive_path)
    folder_on_bucket = "data.gouv.fr"
    path_on_bucket = f"{folder_on_bucket}/{archive_name}"

    # Scaleway S3's maximum number of parts for multipart upload
    MAX_PARTS = 1000
    # compute the corresponding part size
    archive_size = os.path.getsize(archive_path)
    part_size = int(archive_size * 1.2 / MAX_PARTS)
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


def publish_on_data_gouv(public_url, archive_size, archive_sha1):
    # publish the archive on data.gouv.fr
    dataset_id = os.environ.get("DATA_GOUV_DATASET_ID")
    resource_id = data_gouv_resource_id(dataset_id)
    update_resource_metadata(
        dataset_id, resource_id, public_url, archive_size, archive_sha1
    )
    return True


def data_gouv_resource_id(dataset_id):
    # get the resource id from data.gouv.fr
    DATA_GOUV_BASE_URL = os.environ.get("DATA_GOUV_BASE_URL")
    dataset_url = f"{DATA_GOUV_BASE_URL}/api/1/datasets/{dataset_id}/"

    response = requests.get(dataset_url)

    if response.status_code != 200:
        raise Exception("Error while fetching the dataset")
    else:
        res = response.json()
        resources = res["resources"]
        for resource in resources:
            if resource["format"] == "zip":
                return resource["id"]
        raise Exception("No zip resource found on the dataset")


def update_resource_metadata(
    dataset_id, resource_id, public_url, archive_size, archive_sha1
):
    # update the resource url on data.gouv.fr
    DATA_GOUV_BASE_URL = os.environ.get("DATA_GOUV_BASE_URL")
    update_url = (
        f"{DATA_GOUV_BASE_URL}/api/1/datasets/{dataset_id}/resources/{resource_id}/"
    )
    headers = {"X-API-KEY": os.environ.get("DATA_GOUV_API_KEY")}

    response = requests.put(
        update_url,
        headers=headers,
        json={
            "url": public_url,
            "filesize": archive_size,
            "checksum": {"type": "sha1", "value": archive_sha1},
        },
    )

    if response.status_code != 200:
        raise Exception("Error while updating the resource url")
    else:
        return True


def cleanup_directory(directory_name):
    shutil.rmtree(directory_name)
