import json
import os
from datetime import datetime
from unittest import mock

import boto3
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase
from freezegun import freeze_time
from moto import mock_aws

from batid.models import Address
from batid.models import Building
from batid.models import Department
from batid.services.data_gouv_publication import cleanup_directory
from batid.services.data_gouv_publication import create_archive
from batid.services.data_gouv_publication import create_csv
from batid.services.data_gouv_publication import create_directory
from batid.services.data_gouv_publication import data_gouv_create_resource
from batid.services.data_gouv_publication import data_gouv_resource_id
from batid.services.data_gouv_publication import publish_on_data_gouv
from batid.services.data_gouv_publication import update_resource_metadata
from batid.services.data_gouv_publication import upload_to_s3

# Polygone dans Paris
def get_geom():
    coords = {
        "coordinates": [
            [
                [2.335567506457323, 48.86527682329017],
                [2.333737188147865, 48.863794276245784],
                [2.335572829422773, 48.862958671187045],
                [2.334026055739656, 48.862126337971404],
                [2.335567506457323, 48.86527682329017],
            ]
        ],
        "type": "Polygon",
    }

    return GEOSGeometry(json.dumps(coords), srid=4326)


# bbox sur Paris
def get_department_geom():
    coords = {
        "coordinates": [
            [
                [
                    [2.238184771496691, 48.90857365031127],
                    [2.238184771496691, 48.812797283252735],
                    [2.425226858137023, 48.812797283252735],
                    [2.425226858137023, 48.90857365031127],
                    [2.238184771496691, 48.90857365031127],
                ]
            ]
        ],
        "type": "MultiPolygon",
    }
    return GEOSGeometry(json.dumps(coords), srid=4326)


def get_resources():
    json = {
        "resources": [
            {"id": "1", "title": "Export Départemental 33", "format": "csv"},
            {"id": "2", "title": "Export Départemental 33", "format": "zip"},
            {"id": "3", "title": "Export Départemental 75", "format": "zip"},
            {"id": "4", "title": "Export National", "format": "zip"},
        ]
    }
    return json


class TestDataGouvPublication(TestCase):
    def test_archive_creation_deletion(self):
        geom = get_geom()
        department = Department.objects.create(
            code="75", name="Paris", shape=get_department_geom()
        )
        address = Address.objects.create(
            source="BAN",
            point=geom.point_on_surface,
            street_number="4",
            street_name="rue scipion",
            city_name="Paris",
        )
        building = Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom,
            point=geom.point_on_surface,
            ext_ids={"some_source": "1234"},
        )
        building.addresses.add(address)
        building.save()

        directory_name = create_directory()
        area = "75"
        create_csv(directory_name, area)

        # Check if the directory exists
        self.assertTrue(os.path.exists(directory_name))

        # check there is one file in the directory
        files = os.listdir(directory_name)
        self.assertEqual(len(files), 1)

        # open the file and check the content
        with open(f"{directory_name}/RNB_{area}.csv", "r") as f:
            content = f.read()
            self.assertIn(
                "rnb_id;point;shape;ext_ids;addresses",
                content,
            )
            self.assertIn("BDG-CONSTR", content)
            self.assertIn("POLYGON", content)
            self.assertIn("POINT", content)
            self.assertIn("some_source", content)

        (archive_path, archive_size, archive_sha1) = create_archive(
            directory_name, area
        )

        # check the archive exists
        self.assertTrue(os.path.exists(archive_path))
        self.assertEqual(archive_size, os.path.getsize(archive_path))
        # assert sha is not empty
        self.assertTrue(archive_sha1)

        cleanup_directory(directory_name)

        # check the directory has been removed
        self.assertFalse(os.path.exists(directory_name))

    @mock_aws
    # we mock the environnement variables to use the moto library
    # with the default AWS s3 values (could not make it work with custom values)
    @mock.patch.dict(
        os.environ,
        {
            "S3_SCALEWAY_REGION_NAME": "us-east-1",
            "S3_SCALEWAY_ENDPOINT_URL": "https://s3.us-east-1.amazonaws.com",
            "S3_SCALEWAY_BUCKET_NAME": "rnb-opendata",
            "S3_SCALEWAY_OPENDATA_DIRECTORY": "files",
        },
    )
    def test_upload_to_s3(self):
        # create the zip file to upload
        geom = get_geom()
        Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom,
            point=geom.point_on_surface,
            ext_ids={"some_source": "1234"},
        )
        directory_name = create_directory()
        area = "nat"
        create_csv(directory_name, area)

        (archive_path, archive_size, archive_sha1) = create_archive(
            directory_name, area
        )

        # create the mock s3 bucket
        conn = boto3.resource("s3")
        conn.create_bucket(Bucket="rnb-opendata")

        # upload the file to s3
        upload_to_s3(archive_path)

        # check the file exists in data.gouv.fr folder and has the correct size
        archive_name = os.path.basename(archive_path)
        self.assertEqual(
            conn.Object("rnb-opendata", f"files/{archive_name}").content_length,
            archive_size,
        )

        cleanup_directory(directory_name)

    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_get_resource_id_on_data_gouv(self, get_mock):
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = get_resources()

        resource_id = data_gouv_resource_id("some-dataset-id", "33")
        self.assertEqual(resource_id, "2")

        resource_id = data_gouv_resource_id("some-dataset-id", "75")
        self.assertEqual(resource_id, "3")

        resource_id = data_gouv_resource_id("some-dataset-id", "nat")
        self.assertEqual(resource_id, "4")

        resource_id = data_gouv_resource_id("some-dataset-id", "123")
        self.assertIsNone(resource_id)

    @freeze_time("2021-02-23")
    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
        },
    )
    def test_update_resource_on_data_gouv(self, put_mock):
        put_mock.return_value.status_code = 200
        title = "Export du RNB"
        description = "Export du RNB au format csv pour un territoire français."
        public_url = "some-url"
        archive_size = 1234
        archive_sha1 = "some-sha1"
        update_resource_metadata(
            "some-dataset-id",
            "some-resource-id",
            title,
            description,
            public_url,
            archive_size,
            archive_sha1,
            "csv",
        )

        put_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/some-resource-id/",
            headers={
                "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "description": description,
                "type": "main",
                "url": public_url,
                "filetype": "remote",
                "format": "csv",
                "filesize": archive_size,
                "checksum": {"type": "sha1", "value": archive_sha1},
                "last_modified": datetime.now(),
            },
        )

    @freeze_time("2021-02-23")
    @mock.patch("batid.services.data_gouv_publication.requests.post")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
        },
    )
    def test_create_resource_on_data_gouv(self, post_mock):
        post_mock.return_value.status_code = 200
        title = "Export du RNB"
        description = "Export du RNB au format csv pour un territoire français."
        public_url = "some-url"
        archive_size = 1234
        archive_sha1 = "some-sha1"
        format = "csv"
        data_gouv_create_resource(
            "some-dataset-id",
            title,
            description,
            public_url,
            archive_size,
            archive_sha1,
            format,
        )

        post_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/",
            headers={
                "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "description": description,
                "type": "main",
                "url": public_url,
                "filetype": "remote",
                "format": format,
                "filesize": archive_size,
                "checksum": {"type": "sha1", "value": archive_sha1},
                "created_at": datetime.now(),
            },
        )

    # Test publication de ressources existantes
    @freeze_time("2021-02-23")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_publishing_existing_dept_resource_on_data_gouv(self, get_mock, put_mock):
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = get_resources()

        put_mock.return_value.status_code = 200
        department = "33"
        title = f"Export Départemental {department}"
        description = f"Export du RNB au format csv pour le département {department}."
        public_url = "some-url"
        archive_size = 1234
        archive_sha1 = "some-sha1"
        format = "csv"
        publish_on_data_gouv(department, public_url, archive_size, archive_sha1, format)

        put_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/2/",
            headers={
                "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "description": description,
                "type": "main",
                "url": public_url,
                "filetype": "remote",
                "format": format,
                "filesize": archive_size,
                "checksum": {"type": "sha1", "value": archive_sha1},
                "last_modified": datetime.now(),
            },
        )

    @freeze_time("2021-02-23")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_publishing_existing_national_resource_on_data_gouv(
        self, get_mock, put_mock
    ):
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = get_resources()

        put_mock.return_value.status_code = 200
        title = f"Export National"
        description = (
            f"Export du RNB au format csv pour l’ensemble du territoire français."
        )
        public_url = "some-url"
        archive_size = 1234
        archive_sha1 = "some-sha1"
        format = "csv"
        publish_on_data_gouv("nat", public_url, archive_size, archive_sha1, format)

        put_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/4/",
            headers={
                "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "description": description,
                "type": "main",
                "url": public_url,
                "filetype": "remote",
                "format": format,
                "filesize": archive_size,
                "checksum": {"type": "sha1", "value": archive_sha1},
                "last_modified": datetime.now(),
            },
        )

    # Test publication d'une ressource inexistante
    @freeze_time("2021-02-23")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    @mock.patch("batid.services.data_gouv_publication.requests.post")
    def test_publishing_non_existing_resource_on_data_gouv(self, post_mock, get_mock):
        post_mock.return_value.status_code = 200
        post_mock.return_value.json.return_value = 4

        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = get_resources()

        department = "45"
        title = f"Export Départemental {department}"
        description = f"Export du RNB au format csv pour le département {department}."
        public_url = "some-url"
        archive_size = 1234
        archive_sha1 = "some-sha1"
        format = "csv"
        publish_on_data_gouv(department, public_url, archive_size, archive_sha1, format)

        post_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/",
            headers={
                "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "description": description,
                "type": "main",
                "url": public_url,
                "filetype": "remote",
                "format": format,
                "filesize": archive_size,
                "checksum": {"type": "sha1", "value": archive_sha1},
                "created_at": datetime.now(),
            },
        )
