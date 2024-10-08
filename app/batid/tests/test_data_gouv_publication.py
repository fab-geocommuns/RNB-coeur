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
def get_geom_paris():
    coords = {
        "coordinates": [
            [
                [2.353721421744524, 48.83801408684721],
                [2.3538278210596104, 48.83790774339977],
                [2.353989390389472, 48.83797518073416],
                [2.3538810207165, 48.83809708645475],
                [2.353721421744524, 48.83801408684721],
            ]
        ],
        "type": "Polygon",
    }

    return GEOSGeometry(json.dumps(coords), srid=4326)


# Polygone dans Montreuil
def get_geom_montreuil():
    coords = {
        "coordinates": [
            [
                [2.433562579127482, 48.858632940973195],
                [2.4335441278550434, 48.85851518821599],
                [2.433634539088416, 48.858507904531365],
                [2.4336511452333127, 48.858625657305396],
                [2.433562579127482, 48.858632940973195],
            ]
        ],
        "type": "Polygon",
    }

    return GEOSGeometry(json.dumps(coords), srid=4326)


# bbox sur Paris
def get_department_75_geom():
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


# bbox sur Est de Paris
def get_department_93_geom():
    coords = {
        "coordinates": [
            [
                [
                    [2.426210394796641, 48.90890218742271],
                    [2.426210394796641, 48.84215900551669],
                    [2.5026701757286105, 48.84215900551669],
                    [2.5026701757286105, 48.90890218742271],
                    [2.426210394796641, 48.90890218742271],
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
        geom_bdg_paris = get_geom_paris()
        Department.objects.create(
            code="75",
            name="Paris",
            shape=get_department_75_geom(),
        )
        geom_bdg_montreuil = get_geom_montreuil()
        Department.objects.create(
            code="93",
            name="Est",
            shape=get_department_93_geom(),
        )
        address_Paris = Address.objects.create(
            id="75105_8884_00004",
            source="BAN",
            point=geom_bdg_paris.point_on_surface,
            street_number="4",
            street_name="rue scipion",
            city_name="Paris",
            city_zipcode="75005",
        )
        building = Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom_bdg_paris,
            point=geom_bdg_paris.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "1234"},
            addresses_id=[address_Paris.id],
        )
        building.save()

        # building without address
        building = Building.objects.create(
            rnb_id="BDG2-PARIS",
            shape=geom_bdg_paris,
            point=geom_bdg_paris.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "5678"},
        )

        address_Montreuil = Address.objects.create(
            id="93048_1450_00050",
            source="BAN",
            point=geom_bdg_montreuil.point_on_surface,
            street_number="50",
            street_name="boulevard de chanzy",
            city_name="Montreuil",
            city_zipcode="93100",
        )
        building = Building.objects.create(
            rnb_id="BDG-2-CONSTR",
            shape=geom_bdg_montreuil,
            point=geom_bdg_montreuil.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "987"},
            addresses_id=[address_Paris.id, address_Montreuil.id],
        )
        building.save()

        area = "75"
        directory_name = create_directory(area)

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
                "rnb_id;point;shape;status;ext_ids;addresses;addresses_ban_cle_interop\n",
                content,
            )
            self.assertIn("BDG-CONSTR", content)
            self.assertIn("POLYGON", content)
            self.assertIn("POINT", content)
            self.assertIn("constructed", content)
            self.assertIn("some_source", content)
            self.assertIn("75005", content)
            self.assertIn("scipion", content)
            self.assertIn("75105_8884_00004", content)
            # check none address is null and not [""]
            self.assertNotIn('[""]', content)
            self.assertNotIn("93100", content)
            self.assertNotIn("chanzy", content)

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
        geom = get_geom_paris()
        Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom,
            point=geom.point_on_surface,
            ext_ids={"some_source": "1234"},
        )
        area = "nat"
        directory_name = create_directory(area)

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
                "last_modified": str(datetime.now()),
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
        post_mock.return_value.status_code = 201
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
                "created_at": str(datetime.now()),
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
                "last_modified": str(datetime.now()),
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
                "last_modified": str(datetime.now()),
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
        post_mock.return_value.status_code = 201
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
                "created_at": str(datetime.now()),
            },
        )
