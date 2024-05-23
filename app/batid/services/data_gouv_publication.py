import hashlib
import logging
import os
import shutil
from datetime import datetime
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

import boto3
import requests
from django.db import connection


def publish(areas_list):
    # Publish the RNB on data.gouv.fr
    directory_name = create_directory()
    print(str(len(areas_list)) + " area(s) to process...")

    try:
        for area in areas_list:
            print("Processing area: " + area)
            create_csv(directory_name, area)
            (archive_path, archive_size, archive_sha1) = create_archive(
                directory_name, area
            )
            # Delete file after archiving
            os.remove(directory_name + "/rnb_" + area + ".csv")

            public_url = upload_to_s3(archive_path)
            publish_on_data_gouv(area, public_url, archive_size, archive_sha1)
            # Delete archive after pushed on S3
            os.remove(archive_path)
    except Exception as e:
        logging.error(f"Error while publishing the RNB on data.gouv.fr: {e}")
        return False
    finally:
        # we always cleanup the directory, no matter what happens
        cleanup_directory(directory_name)
    return True


def create_directory():
    directory_name = (
        f'datagouvfr_publication_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    )
    os.mkdir(directory_name)
    return directory_name


def create_csv(directory_name, code_area):
    with connection.cursor() as cursor:
        if code_area == "nat":
            sql = "COPY (SELECT rnb_id, point, shape, ext_ids, addresses, code_dept FROM opendata.rnb_compact) TO STDOUT WITH CSV HEADER DELIMITER ';'"
        else:
            sql = (
                "COPY (SELECT rnb_id, point, shape, ext_ids, addresses FROM opendata.rnb_compact WHERE code_dept = '"
                + code_area
                + "') TO STDOUT WITH CSV HEADER DELIMITER ';'"
            )

        with open(f"{directory_name}/rnb_{code_area}.csv", "w") as fp:
            cursor.copy_expert(sql, fp)


def sha1sum(filename):
    h = hashlib.sha1()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()


def create_archive(directory_name, code):
    files = os.listdir(directory_name)
    archive_path = f"{directory_name}/RNB_{code}.csv.zip"

    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zip:
        zip.write(f"{directory_name}/rnb_{code}.csv")

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
    folder_on_bucket = S3_SCALEWAY_OPENDATA_DIRECTORY
    path_on_bucket = f"{folder_on_bucket}/{archive_name}"

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


def publish_on_data_gouv(area, public_url, archive_size, archive_sha1, format=zip):
    # publish the archive on data.gouv.fr
    dataset_id = os.environ.get("DATA_GOUV_DATASET_ID")
    print("values: " + dataset_id + " - " + str(area))
    resource_id = data_gouv_resource_id(dataset_id, area)
    print("ress: " + resource_id)

    if area == "nat":
        title = "Export National"
        description = (
            "Export du RNB au format csv pour l’ensemble du territoire français."
        )
    else:
        title = "Export Départemental " + area
        description = "Export du RNB au format csv pour le département " + area + "."

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
    dataset_id, title, description, public_url, archive_size, archive_sha1, format=zip
):
    # get the resource id from data.gouv.fr
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
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

    if response.status_code != 200:
        raise Exception("Error while creating the resource")

    return True


def data_gouv_resource_id(dataset_id, area):
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
            print(resource["format"])
            print(resource["title"])
            if resource["format"] == "zip" and ((area == "nat" and resource["title"] == "Export National") or (area != "nat" and resource["title"] == "Export Départemental " + area)):
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
            "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

    if response.status_code != 200:
        raise Exception("Error while updating the resource url")
    else:
        return True


def cleanup_directory(directory_name):
    shutil.rmtree(directory_name)
