import json
import os
from unittest import mock

import boto3
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase
from moto import mock_aws

from batid.models import Address
from batid.models import Building
from batid.models import Department
from batid.services.data_gouv_publication import cleanup_directory
from batid.services.data_gouv_publication import create_directory
from batid.services.data_gouv_publication import create_csv
from batid.services.data_gouv_publication import create_archive
from batid.services.data_gouv_publication import upload_to_s3
from batid.services.data_gouv_publication import data_gouv_resource_id
from batid.services.data_gouv_publication import update_resource_metadata
from batid.services.data_gouv_publication import publish_on_data_gouv
from batid.services.data_gouv_publication import data_gouv_create_resource


def get_geom():
    coords = {
        "coordinates": [
            [
            [2.3355675064573234, 48.86527682329017],
            [2.3337371881478646, 48.863794276245784],
            [2.335572829422773, 48.862958671187045],
            [2.334026055739656, 48.862126337971404],
            [2.3355675064573234, 48.86527682329017]
            ]
        ],
        "type": "MultiPolygon",
    }

    return GEOSGeometry(json.dumps(coords), srid=4326)

def get_department_geom():
    coords = {
        "coordinates": [
            [2.238184771496691, 48.90857365031127],
            [2.238184771496691, 48.812797283252735],
            [2.425226858137023, 48.812797283252735],
            [2.425226858137023, 48.90857365031127],
            [2.238184771496691, 48.90857365031127]
          ],
        "type": "MultiPolygon",
    }

    return GEOSGeometry(json.dumps(coords), srid=4326)


class TestDataGouvPublication(TestCase):
    def test_archive_creation_deletion(self):
        geom = get_geom()
        department = Department.objects.create(
            code="75",
            name="Paris",
            shape=get_department_geom()
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
        with open(f"{directory_name}/rnb_{area}.csv", "r") as f:
            content = f.read()
            self.assertIn(
                #"id,rnb_id,point,created_at,updated_at,shape,ext_ids", content
                "rnb_id;geom;bati;external_ids", content
            )
            self.assertIn("BDG-CONSTR", content)
            self.assertIn("MULTIPOLYGON", content)
            self.assertIn("POINT", content)
            self.assertIn("some_source", content)

        (archive_path, archive_size, archive_sha1) = create_archive(directory_name, area)

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
        area = 'nat'
        create_csv(directory_name, area)

        (archive_path, archive_size, archive_sha1) = create_archive(directory_name, area)

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
        get_mock.return_value.json.return_value = {
            "resources": [{"id": "1", "title": "33", "format": "csv"}, {"id": "2", "title": "33", "format": "zip"}]
        }

        resource_id = data_gouv_resource_id("some-dataset-id", "33")
        self.assertEqual(resource_id, "2")

    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
        },
    )
    def test_update_resource_on_data_gouv(self, put_mock):
        put_mock.return_value.status_code = 200
        archive_sha1 = "some-sha1"
        update_resource_metadata(
            "some-dataset-id", "some-resource-id", "some-url", 1234, archive_sha1
        )

        put_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/some-resource-id/",
            headers={"X-API-KEY": os.environ.get("DATA_GOUV_API_KEY")},
            json={
                "url": "some-url",
                "filesize": 1234,
                "checksum": {"type": "sha1", "value": archive_sha1},
            },
        )

    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr"
        },
    )
    def test_create_resource_on_data_gouv(self, put_mock):
        put_mock.return_value.status_code = 200
        title = "Export du RNB"
        description = "Export du RNB au format csv pour un territoire français."
        public_url = "some-url"
        data_gouv_create_resource(
            "some-dataset-id", title, description, public_url, "csv"
        )

        put_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/",
            headers={
                "X-API-KEY": os.environ.get("DATA_GOUV_API_KEY"),
                "Content-Type": "application/json"
                },
            json={
                "title": title,
                "description": description,
                "type": "main",
                "url": public_url,
                "filetype": "remote",
                "format": "csv",
            },
        )

    # Test publication d'une ressource inexistante - A Faire
    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
        },
    )
    def test_publishing_non_existing_resource_on_data_gouv(self, put_mock):
        put_mock.return_value.status_code = 200
        archive_sha1 = "some-sha1"
        publish_on_data_gouv(
            "75", "some-url", 1234, archive_sha1
        )

        put_mock.assert_called_with(
            f"{os.environ.get('DATA_GOUV_BASE_URL')}/api/1/datasets/some-dataset-id/resources/",
            headers={"X-API-KEY": os.environ.get("DATA_GOUV_API_KEY")},
            json={
                "url": "some-url",
                "filesize": 1234,
                "checksum": {"type": "sha1", "value": archive_sha1},
            },
        )