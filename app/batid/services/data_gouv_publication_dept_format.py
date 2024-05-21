import hashlib
import logging
import os
from datetime import datetime
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

import boto3
import requests
from django.db import connection


def publish(depts, format):
    # Publish the RNB on data.gouv.fr
    directory_name = create_directory()
    print(str(len(depts)) + " departments to process...")

    try:
        for dept in depts:
            print("Processing dept: " + dept)
            create_rnb_files(directory_name, dept, format)
            (archive_path, archive_size, archive_sha1) = create_archive(
                directory_name, dept, format
            )
            # Delete file after archiving
            drop_file(directory_name + "/rnb_building_" + dept + "." + format)
            drop_file(directory_name + "/rnb_address_" + dept + "." + format)

            # public_url = upload_to_s3(archive_path)
            # publish_on_data_gouv(public_url, archive_size, archive_sha1)
            # Delete archive after pushed on S3
            drop_file(archive_path)
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


def create_rnb_files(directory_name, code_dept, format):
    if format == "csv":
        create_rnb_csv_files(directory_name, code_dept)


def create_rnb_csv_files(directory_name, code_dept):
    create_building_csv(directory_name, code_dept)
    create_address_csv(directory_name, code_dept)

    return True


def create_building_csv(directory_name, code_dept):
    with connection.cursor() as cursor:
        sql = (
            "COPY (SELECT rnb_id, geom, bati, external_ids FROM opendata.rnb_compact WHERE code_dept = '"
            + code_dept
            + "') TO STDOUT WITH CSV HEADER DELIMITER ';'"
        )

        with open(f"{directory_name}/rnb_building_{code_dept}.csv", "w") as fp:
            cursor.copy_expert(sql, fp)


def create_address_csv(directory_name, code_dept):
    with connection.cursor() as cursor:
        sql = (
            "COPY (SELECT rnb_id, address_code, address_source, street_number, street_rep, street_type, street_name, city_zipcode, city_code, city_name FROM opendata.rnb_addr WHERE city_code LIKE '"
            + code_dept
            + "%') TO STDOUT WITH CSV HEADER DELIMITER ';'"
        )

        with open(f"{directory_name}/rnb_address_{code_dept}.csv", "w") as fp:
            cursor.copy_expert(sql, fp)


def sha1sum(filename):
    h = hashlib.sha1()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()


def create_archive(directory_name, code_dept, format):
    files = os.listdir(directory_name)
    archive_path = f"{directory_name}/RNB_{code_dept}.{format}.zip"

    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zip:
        zip.write(f"{directory_name}/rnb_building_{code_dept}.{format}")
        zip.write(f"{directory_name}/rnb_address_{code_dept}.{format}")

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
    part_size = max(1, int(archive_size * 1.2 / MAX_PARTS))
    print(part_size)
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
    os.removedirs(directory_name)


def drop_file(path):
    os.remove(path)
