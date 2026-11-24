import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from unittest import mock
from zipfile import ZipFile

import boto3
import requests
from batid.models import (
    Address,
    Building,
    Department_subdivided,
    Organization,
    Plot,
    UserProfile,
)
from batid.services import data_gouv_publication
from batid.services.administrative_areas import dpts_list
from batid.services.data_gouv_publication import (
    DATA_GOUV_TIMEOUT_S,
    RUN_DIRECTORY_PREFIX,
    DataGouvAccessDenied,
    NationalArchiveError,
    build_department_archive,
    cleanup_directory,
    create_archive,
    create_directory,
    create_national_archive,
    csv_records,
    data_gouv_create_resource,
    data_gouv_resource_id,
    department_archive_path,
    get_area_publish_task,
    publish,
    publish_on_data_gouv,
    publish_on_data_gouv_with_retries,
    remove_previous_run_directories,
    run_directory,
    update_resource_metadata,
    upload_to_s3,
)
from batid.services.tchap import Code, TchapLevel
from batid.tasks import publish_datagouv_all, publish_datagouv_national
from batid.tests.factories.users import ContributorUserFactory
from celery import chain
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from freezegun import freeze_time
from moto import mock_aws

from app.settings import WRITABLE_DATA_DIR


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
                [2.238184771496691, 48.90857365031127],
                [2.238184771496691, 48.812797283252735],
                [2.425226858137023, 48.812797283252735],
                [2.425226858137023, 48.90857365031127],
                [2.238184771496691, 48.90857365031127],
            ]
        ],
        "type": "Polygon",
    }
    return GEOSGeometry(json.dumps(coords), srid=4326)


# bbox sur Est de Paris
def get_department_93_geom():
    coords = {
        "coordinates": [
            [
                [2.426210394796641, 48.90890218742271],
                [2.426210394796641, 48.84215900551669],
                [2.5026701757286105, 48.84215900551669],
                [2.5026701757286105, 48.90890218742271],
                [2.426210394796641, 48.90890218742271],
            ]
        ],
        "type": "Polygon",
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

    def setUp(self):

        # Create a user with an organization
        self.user_1 = ContributorUserFactory(
            first_name="El",
            last_name="Validator",
            username="el_validator",
        )

        self.org = Organization.objects.create(name="Comité de validation")
        profile, _ = UserProfile.objects.get_or_create(user=self.user_1)
        profile.organization = self.org
        profile.save(update_fields=["organization"])

        # Create a user without organization
        self.user_2 = ContributorUserFactory(
            first_name="Jean",
            last_name="Doux",
            username="jean_doux",
        )

    def test_csv_written_as_utf8_bytes(self):
        """
        Input: one building linked to an address on "rue de l'Église".
        Expected: the raw bytes of the RNB_75.csv zip entry decode as UTF-8
        and contain "Église".
        """
        address = Address.objects.create(
            cle_interop="75105_0001_00001", street="rue de l'Église"
        )
        Department_subdivided.objects.create(
            code="75", name="Paris", shape=get_department_75_geom()
        )
        geom = get_geom_paris()
        Building.objects.create(
            rnb_id="BDG-ACCENT01",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            addresses_internal_id=[address.internal_id],
        )
        directory_name = create_directory("75")
        self.addCleanup(cleanup_directory, directory_name)

        archive_path, _, _ = create_archive(directory_name, "75")

        with ZipFile(archive_path) as archive:
            raw = archive.read("RNB_75.csv")
        self.assertIn("Église".encode("utf-8"), raw)
        raw.decode("utf-8")

    def test_building_on_subdivision_edge_exported_once(self):
        """
        Input: department 75 split into two adjacent squares; one active building
        whose point lies on their shared edge, linked to one address.
        Expected: RNB_75.csv holds a single row for it, with that address once.
        """
        address = Address.objects.create(cle_interop="75105_0001_00001")
        Department_subdivided.objects.create(
            code="75",
            name="Paris",
            shape=GEOSGeometry("POLYGON((2 48, 3 48, 3 49, 2 49, 2 48))", srid=4326),
        )
        Department_subdivided.objects.create(
            code="75",
            name="Paris",
            shape=GEOSGeometry("POLYGON((3 48, 4 48, 4 49, 3 49, 3 48))", srid=4326),
        )
        Building.objects.create(
            rnb_id="BDG-ON-EDGE",
            shape=GEOSGeometry("POINT(3 48.5)", srid=4326),
            point=GEOSGeometry("POINT(3 48.5)", srid=4326),
            status="constructed",
            addresses_internal_id=[address.internal_id],
        )
        directory_name = create_directory("75")
        self.addCleanup(cleanup_directory, directory_name)

        archive_path, _, _ = create_archive(directory_name, "75")

        with ZipFile(archive_path) as archive, io.TextIOWrapper(
            archive.open("RNB_75.csv"), encoding="utf-8", newline=""
        ) as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        self.assertEqual([row["rnb_id"] for row in rows], ["BDG-ON-EDGE"])
        self.assertEqual(
            [a["cle_interop_ban"] for a in json.loads(rows[0]["addresses"])],
            ["75105_0001_00001"],
        )

    def test_archive_creation_deletion(self):
        """
        Input: several Parisian buildings (active/inactive, 0/1/many addresses,
        validated by 0, 1 or 2 users), plots and the 75 and 93 departments;
        the zip export of area "75" is generated.

        Expected: the directory holds only RNB_75.csv.zip (no CSV on disk); the
        zip is valid, has a single RNB_75.csv entry dated at export time, and
        that CSV contains only the 3 active buildings of the 75. Returned size
        and sha1 match the zip file. The directory is then cleaned up.
        """

        self.maxDiff = None

        geom_bdg_paris = get_geom_paris()
        geom_bdg_montreuil = get_geom_montreuil()

        # Departements
        Department_subdivided.objects.create(
            code="75",
            name="Paris",
            shape=get_department_75_geom(),
        )
        Department_subdivided.objects.create(
            code="93",
            name="Est",
            shape=get_department_93_geom(),
        )

        # Address
        address_paris_1 = Address.objects.create(
            cle_interop="75105_8884_00004",
            source="BAN",
            point=geom_bdg_paris.point_on_surface,
            street_number="4",
            street="rue scipion",
            city_name="Paris",
            city_zipcode="75005",
        )

        address_paris_2 = Address.objects.create(
            cle_interop="75105_8884_00005",
            source="BAN",
            point=geom_bdg_paris.point_on_surface,
            street_number="6",
            street="rue hello",
            city_name="Paris",
            city_zipcode="75020",
        )

        # Building 1: should be in CSV
        Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom_bdg_paris,
            point=geom_bdg_paris.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "1234"},
            addresses_internal_id=[address_paris_1.internal_id],
            is_active=True,
            validated_by=[self.user_1.id],
        )

        # Building 2: is inactive, should not be in the csv
        Building.objects.create(
            rnb_id="BDG-INACTIVE",
            shape=geom_bdg_paris,
            point=geom_bdg_paris.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "1234"},
            addresses_internal_id=[address_paris_1.internal_id],
            is_active=False,
        )

        # Building 3: without address
        Building.objects.create(
            rnb_id="BDG2-PARIS",
            shape=geom_bdg_paris,
            point=geom_bdg_paris.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "5678"},
            validated_by=[self.user_1.id, self.user_2.id],
        )

        # Building 4: many addresses
        Building.objects.create(
            rnb_id="BDG-MANY-ADD",
            shape=geom_bdg_paris.point_on_surface,
            point=geom_bdg_paris.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "9999"},
            addresses_internal_id=[
                address_paris_1.internal_id,
                address_paris_2.internal_id,
            ],
        )

        address_Montreuil = Address.objects.create(
            cle_interop="93048_1450_00050",
            source="BAN",
            point=geom_bdg_montreuil.point_on_surface,
            street_number="50",
            street="boulevard de chanzy",
            city_name="Montreuil",
            city_zipcode="93100",
        )
        Building.objects.create(
            rnb_id="BDG-2-CONSTR",
            shape=geom_bdg_montreuil,
            point=geom_bdg_montreuil.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "987"},
            addresses_internal_id=[
                address_paris_1.internal_id,
                address_Montreuil.internal_id,
            ],
        )

        # create 2 plots touching the Parisian building
        # plot 1
        Plot.objects.create(
            id="plot_1",
            shape="MULTIPOLYGON (((2.353592263942687 48.8381199933757, 2.353592263942687 48.83800449764507, 2.354083199327647 48.83800449764507, 2.354083199327647 48.8381199933757, 2.353592263942687 48.8381199933757)))",
        )

        # # plot 2
        Plot.objects.create(
            id="plot_2",
            shape="MULTIPOLYGON (((2.3535922986454807 48.838004770495814, 2.3535922986454807 48.83790342816005, 2.354083657770417 48.83790342816005, 2.354083657770417 48.838004770495814, 2.3535922986454807 48.838004770495814)))",
        )

        area = "75"
        directory_name = create_directory(area)

        # even second: zip timestamps have a 2-second resolution
        with freeze_time("2026-03-14 12:34:56"):
            archive_path, archive_size, archive_sha1 = create_archive(
                directory_name, area
            )

        # Check if the directory exists
        self.assertTrue(os.path.exists(directory_name))

        # only the zip is on disk, no intermediate CSV
        self.assertEqual(os.listdir(directory_name), ["RNB_75.csv.zip"])

        with ZipFile(archive_path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), ["RNB_75.csv"])
            self.assertEqual(
                archive.getinfo("RNB_75.csv").date_time, (2026, 3, 14, 12, 34, 56)
            )
            self.assertEqual(
                archive.getinfo("RNB_75.csv").external_attr >> 16, 0o100644
            )

        # Expected values
        expected_keys = [
            "rnb_id",
            "point",
            "shape",
            "status",
            "ext_ids",
            "addresses",
            "plots",
            "validated_by",
        ]
        expected_len = 3
        expected_rows = [
            {
                "rnb_id": "BDG-CONSTR",
                "point": "SRID=4326;POINT(2.353856491181528 48.837994633790686)",
                "shape": "SRID=4326;POLYGON((2.353721421744524 48.83801408684721,2.35382782105961 48.83790774339977,2.353989390389472 48.83797518073416,2.3538810207165 48.83809708645475,2.353721421744524 48.83801408684721))",
                "status": "constructed",
                "ext_ids": {"some_source": "1234"},
                "addresses": [
                    {
                        "cle_interop_ban": "75105_8884_00004",
                        "street_number": "4",
                        "street_rep": None,
                        "street": "rue scipion",
                        "city_zipcode": "75005",
                        "city_name": "Paris",
                    }
                ],
                # the building sits on two plots
                "plots": """[{"id" : "plot_1", "bdg_cover_ratio" : 0.4513785723301588}, {"id" : "plot_2", "bdg_cover_ratio" : 0.5510222422494555}]""",
                "validated_by": [
                    {
                        "id": self.user_1.id,
                        "username": "el_validator",
                        "organization_name": "Comité de validation",
                        "organization_short_name": None,
                    },
                ],
            },
            {
                "rnb_id": "BDG2-PARIS",
                "point": "SRID=4326;POINT(2.353856491181528 48.837994633790686)",
                "shape": "SRID=4326;POLYGON((2.353721421744524 48.83801408684721,2.35382782105961 48.83790774339977,2.353989390389472 48.83797518073416,2.3538810207165 48.83809708645475,2.353721421744524 48.83801408684721))",
                "status": "constructed",
                "ext_ids": {"some_source": "5678"},
                "addresses": [],
                "plots": """[{"id" : "plot_1", "bdg_cover_ratio" : 0.4513785723301588}, {"id" : "plot_2", "bdg_cover_ratio" : 0.5510222422494555}]""",
                "validated_by": [
                    {
                        "id": self.user_1.id,
                        "username": "el_validator",
                        "organization_name": "Comité de validation",
                        "organization_short_name": None,
                    },
                    {
                        "id": self.user_2.id,
                        "username": "jean_doux",
                        "organization_name": None,
                        "organization_short_name": None,
                    },
                ],
            },
            {
                "rnb_id": "BDG-MANY-ADD",
                "point": "SRID=4326;POINT(2.353856491181528 48.837994633790686)",
                "shape": "SRID=4326;POINT(2.353856491181528 48.837994633790686)",
                "status": "constructed",
                "ext_ids": {"some_source": "9999"},
                "addresses": [
                    {
                        "cle_interop_ban": "75105_8884_00004",
                        "street_number": "4",
                        "street_rep": None,
                        "street": "rue scipion",
                        "city_zipcode": "75005",
                        "city_name": "Paris",
                    },
                    {
                        "cle_interop_ban": "75105_8884_00005",
                        "street_number": "6",
                        "street_rep": None,
                        "street": "rue hello",
                        "city_zipcode": "75020",
                        "city_name": "Paris",
                    },
                ],
                # we check the cover ratio for points is 1
                "plots": """[{"id" : "plot_2", "bdg_cover_ratio" : 1}]""",
                "validated_by": [],
            },
        ]
        expected_rows = sorted(expected_rows, key=lambda x: x["rnb_id"])

        # open the CSV entry of the zip and check the content
        with ZipFile(archive_path) as archive, io.TextIOWrapper(
            archive.open(f"RNB_{area}.csv"), encoding="utf-8", newline=""
        ) as f:

            # For the sake of test, we sort both rows and expected rows
            reader = csv.DictReader(f, delimiter=";")
            rows = sorted(list(reader), key=lambda x: x["rnb_id"])

            # We have to convert JSON string in the CSV to compare the values to expected values
            # This is also an implicit test of the JSON good serialization
            for row in rows:
                row["addresses"] = json.loads(row["addresses"])
                row["ext_ids"] = json.loads(row["ext_ids"])
                row["validated_by"] = json.loads(row["validated_by"])

            # First, check all keys
            self.assertListEqual(list(reader.fieldnames), expected_keys)

            # Then, check the length of the rows
            self.assertEqual(len(rows), expected_len)

            # Finally, check the content of the rows
            self.assertListEqual(rows, expected_rows)

        # check the archive exists
        self.assertTrue(os.path.exists(archive_path))
        self.assertEqual(archive_size, os.path.getsize(archive_path))
        with open(archive_path, "rb") as archive_file:
            self.assertEqual(
                archive_sha1, hashlib.sha1(archive_file.read()).hexdigest()
            )
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
        """
        Input: department 75 with one building, its archive built, an empty mocked
        S3 bucket.
        Expected: the archive holds the building and is uploaded under
        files/<archive name> with the archive size.
        """
        Department_subdivided.objects.create(
            code="75", name="Paris", shape=get_department_75_geom()
        )
        geom = get_geom_paris()
        Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom,
            point=geom.point_on_surface,
            ext_ids={"some_source": "1234"},
        )
        area = "75"
        directory_name = create_directory(area)

        archive_path, archive_size, archive_sha1 = create_archive(directory_name, area)
        self.assertIn(b"BDG-CONSTR", map(record_id, zip_records(archive_path)))

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
        """
        Update of an existing resource metadata.
        Expected: one PUT on the resource URL with the metadata and the data.gouv.fr timeout.
        """
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
                "extras": {"analysis:last-modified-at": str(datetime.now())},
            },
            timeout=DATA_GOUV_TIMEOUT_S,
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
        """
        Creation of a new resource in the dataset.
        Expected: one POST on the resources URL with the metadata and the data.gouv.fr timeout.
        """
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
            timeout=DATA_GOUV_TIMEOUT_S,
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
        """
        Publication of department 33, whose zip resource already exists (id 2).
        Expected: PUT on resource 2 with the department title and the data.gouv.fr timeout.
        """
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
                "extras": {"analysis:last-modified-at": str(datetime.now())},
            },
            timeout=DATA_GOUV_TIMEOUT_S,
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
        """
        Publication of the national export, whose zip resource already exists (id 4).
        Expected: PUT on resource 4 with the national title and the data.gouv.fr timeout.
        """
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
                "extras": {"analysis:last-modified-at": str(datetime.now())},
            },
            timeout=DATA_GOUV_TIMEOUT_S,
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
        """
        Publication of department 45, which has no resource yet.
        Expected: POST of a new resource with the department title and the data.gouv.fr timeout.
        """
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
            timeout=DATA_GOUV_TIMEOUT_S,
        )

    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.time.sleep")
    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_publish_retries_network_error_then_succeeds(
        self, get_mock, put_mock, sleep_mock
    ):
        """
        Department 33: the first GET raises a network error, the second one succeeds.
        Expected: the resource is updated once (one PUT) after a single 60 s wait.
        """
        get_mock.side_effect = [
            requests.ConnectionError(),
            mock.Mock(status_code=200, json=mock.Mock(return_value=get_resources())),
        ]
        put_mock.return_value.status_code = 200

        publish_on_data_gouv_with_retries(
            area="33",
            public_url="some-url",
            archive_size=1234,
            archive_sha1="some-sha1",
        )

        put_mock.assert_called_once()
        sleep_mock.assert_called_once_with(60)

    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_API_KEY": "DATA_GOUV_API_KEY",
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.time.sleep")
    @mock.patch("batid.services.data_gouv_publication.requests.put")
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_publish_retries_unavailable_data_gouv_then_succeeds(
        self, get_mock, put_mock, sleep_mock
    ):
        """
        Department 33: the first GET answers 503, the first PUT raises a redirect loop,
        then data.gouv.fr is back.
        Expected: the resource is updated after two waits of 60 then 120 s.
        """
        get_mock.side_effect = [
            mock.Mock(status_code=503, text="<html>maintenance</html>"),
            mock.Mock(status_code=200, json=mock.Mock(return_value=get_resources())),
            mock.Mock(status_code=200, json=mock.Mock(return_value=get_resources())),
        ]
        put_mock.side_effect = [
            requests.TooManyRedirects("Exceeded 30 redirects."),
            mock.Mock(status_code=200),
        ]

        publish_on_data_gouv_with_retries(
            area="33",
            public_url="some-url",
            archive_size=1234,
            archive_sha1="some-sha1",
        )

        self.assertEqual(put_mock.call_count, 2)
        self.assertEqual(sleep_mock.call_args_list, [mock.call(60), mock.call(120)])

    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.time.sleep")
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_publish_gives_up_after_five_network_errors(self, get_mock, sleep_mock):
        """
        Department 33: every GET raises a network error.
        Expected: 5 attempts with waits of 60, 120, 240 and 480 s, then the network
        error is raised.
        """
        get_mock.side_effect = requests.ConnectionError()

        with self.assertRaises(requests.ConnectionError):
            publish_on_data_gouv_with_retries(
                area="33",
                public_url="some-url",
                archive_size=1234,
                archive_sha1="some-sha1",
            )

        self.assertEqual(get_mock.call_count, 5)
        self.assertEqual(
            sleep_mock.call_args_list,
            [mock.call(60), mock.call(120), mock.call(240), mock.call(480)],
        )

    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_BASE_URL": "https://data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.time.sleep")
    @mock.patch("batid.services.data_gouv_publication.requests.get")
    def test_publish_does_not_retry_on_http_error_status(self, get_mock, sleep_mock):
        """
        Department 33: the GET answers with an HTTP 400 status.
        Expected: the error is raised at once, one GET and no wait.
        """
        get_mock.return_value.status_code = 400

        with self.assertRaisesRegex(Exception, "HTTP 400"):
            publish_on_data_gouv_with_retries(
                area="33",
                public_url="some-url",
                archive_size=1234,
                archive_sha1="some-sha1",
            )

        get_mock.assert_called_once()
        sleep_mock.assert_not_called()

    @mock.patch.dict(
        os.environ,
        {
            "DATA_GOUV_BASE_URL": "data.gouv.fr",
            "DATA_GOUV_DATASET_ID": "some-dataset-id",
        },
    )
    @mock.patch("batid.services.data_gouv_publication.time.sleep")
    def test_publish_does_not_retry_on_invalid_url(self, sleep_mock):
        """
        Department 33: DATA_GOUV_BASE_URL has no scheme, requests raises MissingSchema
        before sending anything.
        Expected: MissingSchema is raised at once, with no wait.
        """
        with self.assertRaises(requests.exceptions.MissingSchema):
            publish_on_data_gouv_with_retries(
                area="33",
                public_url="some-url",
                archive_size=1234,
                archive_sha1="some-sha1",
            )

        sleep_mock.assert_not_called()

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "false"})
    @mock.patch("batid.services.data_gouv_publication.upload_to_s3")
    @mock.patch(
        "batid.services.data_gouv_publication.create_archive",
        return_value=("archive.zip", 1, "sha1"),
    )
    @mock.patch("batid.services.data_gouv_publication.cleanup_directory")
    @mock.patch("batid.services.data_gouv_publication.create_directory")
    def test_publish_returns_false_when_disabled(
        self, create_directory_mock, cleanup_mock, create_archive_mock, upload_mock
    ):
        """
        Input: publish(area="33") with ENABLE_DATAGOUV_PUBLICATION="false".
        Expected: False, nothing uploaded.
        """
        self.assertFalse(publish(area="33"))
        upload_mock.assert_not_called()

    @mock.patch(
        "batid.services.data_gouv_publication.create_directory",
        side_effect=OSError(28, "No space left on device"),
    )
    def test_publish_raises_directory_creation_error(self, create_directory_mock):
        """
        Department 33: creating the working directory raises OSError 28 (disk full).
        Expected: publish raises that OSError, not an UnboundLocalError from the cleanup.
        """
        with self.assertRaises(OSError) as ctx:
            publish(area="33")

        self.assertEqual(ctx.exception.errno, 28)

    def create_paris_building(self):
        Department_subdivided.objects.create(
            code="75", name="Paris", shape=get_department_75_geom()
        )
        geom = get_geom_paris()
        Building.objects.create(
            rnb_id="BDG-RUN-75",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
        )

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "false"})
    def test_department_of_a_run_keeps_its_archive(self):
        """
        Input: one Parisian building, publish(area="75", run_id=<run>), publication
        disabled.
        Expected: the run directory holds exactly RNB_75.csv.zip, whose RNB_75.csv
        lists the building; no other entry is left in the data directory (the
        working directory is removed).
        """
        self.create_paris_building()
        run_id = uuid.uuid4().hex
        run_dir = run_directory(run_id)
        self.addCleanup(shutil.rmtree, run_dir, ignore_errors=True)
        entries_before = data_dir_entries()

        publish(area="75", run_id=run_id)

        self.assertEqual(os.listdir(run_dir), ["RNB_75.csv.zip"])
        self.assertEqual(
            data_dir_entries() - entries_before, {os.path.basename(run_dir)}
        )
        with ZipFile(os.path.join(run_dir, "RNB_75.csv.zip")) as archive:
            self.assertIn(b"BDG-RUN-75", archive.read("RNB_75.csv"))

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "false"})
    def test_department_without_run_keeps_nothing(self):
        """
        Input: one Parisian building, publish(area="75") without run id, publication
        disabled.
        Expected: no new entry is left in the data directory.
        """
        self.create_paris_building()
        entries_before = data_dir_entries()

        publish(area="75")

        self.assertEqual(data_dir_entries(), entries_before)

    @mock.patch(
        "batid.services.data_gouv_publication.create_archive",
        side_effect=Exception("copy failed"),
    )
    def test_failed_department_export_keeps_nothing(self, create_archive_mock):
        """
        Input: publish(area="75", run_id=<run>), the archive build raising.
        Expected: the error is raised, no RNB_75.csv.zip in the run directory and no
        new entry left in the data directory.
        """
        run_id = uuid.uuid4().hex
        run_dir = run_directory(run_id)
        self.addCleanup(shutil.rmtree, run_dir, ignore_errors=True)
        entries_before = data_dir_entries()

        with self.assertRaisesRegex(Exception, "copy failed"):
            publish(area="75", run_id=run_id)

        self.assertFalse(
            os.path.exists(department_archive_path(run_dir=run_dir, dept="75"))
        )
        self.assertEqual(data_dir_entries(), entries_before)

    @mock.patch("batid.services.data_gouv_publication.send_archive", return_value=True)
    @mock.patch(
        "batid.services.data_gouv_publication.create_national_archive",
        side_effect=[
            ("RNB_nat.csv.zip", 3, "sha1"),
            NationalArchiveError("assembly failed"),
            ("RNB_nat.csv.zip", 3, "sha1"),
        ],
    )
    def test_failed_run_directory_removal_keeps_the_national_outcome(
        self, create_national_mock, send_mock
    ):
        """
        Input: publish(area="nat", run_id=<run>) with a run directory whose removal
        raises PermissionError, once after a successful publication, once after the
        assembly raised; then once with no run directory at all.
        Expected: True for the published file, the assembly error for the failed one,
        the removal error logged each time; the missing run directory logs nothing.
        """
        data_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, data_dir)
        real_rmdir = os.rmdir

        # shutil.rmtree removes every directory through os.rmdir
        def rmdir_denied_on_runs(path, *args, **kwargs):
            if os.path.basename(path).startswith(RUN_DIRECTORY_PREFIX):
                raise PermissionError(f"cannot remove {path}")
            return real_rmdir(path, *args, **kwargs)

        with mock.patch(
            "batid.services.data_gouv_publication.WRITABLE_DATA_DIR", data_dir
        ):
            run_id = uuid.uuid4().hex
            run_dir = run_directory(run_id)
            os.makedirs(run_dir)
            with mock.patch("os.rmdir", side_effect=rmdir_denied_on_runs):
                with self.assertLogs(level="ERROR") as published_logs:
                    self.assertTrue(publish(area="nat", run_id=run_id))
                with self.assertLogs(level="ERROR") as failed_logs:
                    with self.assertRaisesRegex(
                        NationalArchiveError, "assembly failed"
                    ):
                        publish(area="nat", run_id=run_id)

            with self.assertNoLogs(level="ERROR"):
                self.assertTrue(publish(area="nat", run_id=uuid.uuid4().hex))

        for logs in (published_logs, failed_logs):
            self.assertIn(run_dir, "\n".join(logs.output))

    def test_working_directories_created_in_the_same_second_differ(self):
        """
        Input: create_directory("nat") called twice within one frozen second (a
        manual national launched while the chain's one starts).
        Expected: two distinct existing directories, so that the first run to finish
        does not remove the directory of the other.
        """
        data_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, data_dir)

        with mock.patch(
            "batid.services.data_gouv_publication.WRITABLE_DATA_DIR", data_dir
        ):
            with freeze_time("2026-11-28 10:00:00"):
                first = create_directory("nat")
                second = create_directory("nat")

        self.assertNotEqual(first, second)
        self.assertTrue(os.path.isdir(first))
        self.assertTrue(os.path.isdir(second))


def data_dir_entries():
    return set(os.listdir(WRITABLE_DATA_DIR))


def fail_on_49(*, area, run_id=None):
    if area == "49":
        raise Exception("boom")
    return True


def deny_on_49(*, area, run_id=None):
    if area == "49":
        raise DataGouvAccessDenied("Error while updating the resource url: HTTP 403")
    return True


class TestDataGouvPublishTasks(TestCase):
    @mock.patch("batid.tasks.notify_tech")
    @mock.patch("batid.tasks.publish", side_effect=fail_on_49)
    def test_failing_department_does_not_stop_the_chain(
        self, publish_mock, notify_tech_mock
    ):
        """
        Chain of departments 49 then 50, the publication of 49 raises.
        Expected: 50 is still published and the chain ends with "done"; one Tchap
        failure message for zone 49 carrying the error "boom", and one ERROR record
        with the stack trace is logged.
        """
        with self.assertLogs("batid.tasks", level="ERROR") as logs:
            result = chain(
                get_area_publish_task("49"), get_area_publish_task("50")
            ).apply()

        self.assertEqual(
            publish_mock.call_args_list,
            [
                mock.call(area="49", run_id=None),
                mock.call(area="50", run_id=None),
            ],
        )
        self.assertEqual(result.get(), "done")
        notify_tech_mock.assert_called_once()
        kwargs = notify_tech_mock.call_args.kwargs
        self.assertEqual(kwargs["title"], "Échec de la publication data.gouv")
        self.assertEqual(kwargs["details"], [("Zone", "49")])
        self.assertEqual(kwargs["error"], "boom")
        self.assertEqual(len(logs.records), 1)
        self.assertIsNotNone(logs.records[0].exc_info)

    @mock.patch("batid.tasks.notify_tech", side_effect=Exception("tchap down"))
    @mock.patch("batid.tasks.publish", side_effect=fail_on_49)
    def test_tchap_failure_does_not_stop_the_chain(
        self, publish_mock, notify_tech_mock
    ):
        """
        Chain of departments 49 then 50, the publication of 49 and the Tchap
        notification both raise.
        Expected: 50 is still published; two ERROR records are logged (publication,
        then Tchap).
        """
        with self.assertLogs("batid.tasks", level="ERROR") as logs:
            chain(get_area_publish_task("49"), get_area_publish_task("50")).apply()

        self.assertEqual(
            publish_mock.call_args_list,
            [
                mock.call(area="49", run_id=None),
                mock.call(area="50", run_id=None),
            ],
        )
        self.assertEqual(len(logs.records), 2)

    @mock.patch("batid.tasks.notify_tech")
    @mock.patch("batid.tasks.publish", side_effect=deny_on_49)
    def test_access_denied_stops_the_chain(self, publish_mock, notify_tech_mock):
        """
        Chain of departments 49 then 50, data.gouv.fr refuses the key (403) on 49.
        Expected: the chain raises DataGouvAccessDenied, 50 is not published and no
        per-area Tchap message is sent.
        """
        with self.assertRaises(DataGouvAccessDenied):
            chain(get_area_publish_task("49"), get_area_publish_task("50")).apply()

        self.assertEqual(
            publish_mock.call_args_list, [mock.call(area="49", run_id=None)]
        )
        notify_tech_mock.assert_not_called()

    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", return_value=True)
    def test_summary_after_a_complete_run(self, publish_mock, summary_mock):
        """
        Input: chain of 49, 50 and the national file under one run id, all published.
        Expected: one summary "Publication data.gouv terminée" counting 3 published
        zones out of every department plus the national file; SUCCESS only when
        the count reaches that total, so ALERT here.
        """
        run_id = uuid.uuid4().hex
        total = len(dpts_list()) + 1

        chain(
            get_area_publish_task("49", run_id=run_id),
            get_area_publish_task("50", run_id=run_id),
            get_area_publish_task("nat", run_id=run_id),
        ).apply()

        self.assertEqual(
            publish_mock.call_args_list,
            [
                mock.call(area="49", run_id=run_id),
                mock.call(area="50", run_id=run_id),
                mock.call(area="nat", run_id=run_id),
            ],
        )
        summary_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv terminée",
            details=[("Zones publiées", f"3 sur {total}")],
        )

    @mock.patch("batid.tasks.dpts_list", return_value=["49", "50"])
    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", return_value=True)
    def test_summary_success_when_every_zone_is_published(
        self, publish_mock, summary_mock, dpts_list_mock
    ):
        """
        Input: departments limited to 49 and 50, chain of 49, 50 and the national
        file under one run id, all published.
        Expected: one SUCCESS summary "Publication data.gouv terminée" with
        "3 sur 3".
        """
        run_id = uuid.uuid4().hex

        chain(
            get_area_publish_task("49", run_id=run_id),
            get_area_publish_task("50", run_id=run_id),
            get_area_publish_task("nat", run_id=run_id),
        ).apply()

        summary_mock.assert_called_once_with(
            level=TchapLevel.SUCCESS,
            title="Publication data.gouv terminée",
            details=[("Zones publiées", "3 sur 3")],
        )

    @mock.patch("batid.tasks.notify_tech")
    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", side_effect=fail_on_49)
    def test_summary_alerts_on_a_failed_zone(
        self, publish_mock, summary_mock, notify_tech_mock
    ):
        """
        Input: chain of 49, 50 and the national file under one run id, 49 fails.
        Expected: the per-zone failure message for 49, then one ALERT summary
        counting 2 published zones.
        """
        run_id = uuid.uuid4().hex
        total = len(dpts_list()) + 1

        with self.assertLogs("batid.tasks", level="ERROR"):
            chain(
                get_area_publish_task("49", run_id=run_id),
                get_area_publish_task("50", run_id=run_id),
                get_area_publish_task("nat", run_id=run_id),
            ).apply()

        notify_tech_mock.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la publication data.gouv",
            details=[("Zone", "49")],
            error="boom",
        )
        summary_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv terminée",
            details=[("Zones publiées", f"2 sur {total}")],
        )

    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", return_value=False)
    def test_disabled_publication_is_not_counted(self, publish_mock, summary_mock):
        """
        Input: the national file under a run id, publish returning False (the flag
        was turned off after the launch, nothing sent to data.gouv.fr).
        Expected: the zone is not counted, the summary alerts with 0 published zones.
        """
        run_id = uuid.uuid4().hex
        total = len(dpts_list()) + 1

        get_area_publish_task("nat", run_id=run_id).apply()

        summary_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv terminée",
            details=[("Zones publiées", f"0 sur {total}")],
        )

    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", return_value=True)
    def test_no_summary_without_run_id(self, publish_mock, summary_mock):
        """
        Input: chain of 50 and the national file without run id (the manual
        publish_opendata path).
        Expected: both published, no summary message.
        """
        chain(get_area_publish_task("50"), get_area_publish_task("nat")).apply()

        self.assertEqual(
            publish_mock.call_args_list,
            [
                mock.call(area="50", run_id=None),
                mock.call(area="nat", run_id=None),
            ],
        )
        summary_mock.assert_not_called()

    @mock.patch("batid.tasks.cache.incr", side_effect=Exception("redis down"))
    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", return_value=True)
    def test_count_failure_does_not_stop_the_run(
        self, publish_mock, summary_mock, incr_mock
    ):
        """
        Input: the national file published under a run id, the cache raising on the
        count.
        Expected: the task ends with "done", one ERROR record is logged and the
        summary alerts with 0 published zones.
        """
        run_id = uuid.uuid4().hex
        total = len(dpts_list()) + 1

        with self.assertLogs("batid.tasks", level="ERROR") as logs:
            result = get_area_publish_task("nat", run_id=run_id).apply()

        self.assertEqual(result.get(), "done")
        self.assertEqual(len(logs.records), 1)
        summary_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv terminée",
            details=[("Zones publiées", f"0 sur {total}")],
        )

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "unix:///nonexistent/redis.sock",
            }
        }
    )
    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.publish", return_value=True)
    def test_unreachable_cache_does_not_fail_the_national_task(
        self, publish_mock, summary_mock
    ):
        """
        Input: the national file published under a run id, the cache pointing to a
        Redis socket that cannot exist (count and read both fail).
        Expected: the task ends with "done" instead of failing after the
        publication, and the summary alerts with an unknown count.
        """
        run_id = uuid.uuid4().hex
        total = len(dpts_list()) + 1

        with self.assertLogs("batid.tasks", level="ERROR") as logs:
            result = get_area_publish_task("nat", run_id=run_id).apply()

        self.assertEqual(result.get(), "done")
        self.assertEqual(len(logs.records), 2)
        summary_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv terminée",
            details=[("Zones publiées", f"inconnu sur {total}")],
        )


class TestDataGouvPublicationFlag(TestCase):
    @mock.patch("batid.tasks.chain")
    @mock.patch("batid.tasks.notify_tech")
    def test_unset_flag_launches_nothing(self, notify_tech_mock, chain_mock):
        """
        Input: publish_datagouv_all with ENABLE_DATAGOUV_PUBLICATION unset.
        Expected: no chain queued, one alert "Publication data.gouv non lancée"
        naming the variable and "non définie" as its value.
        """
        with mock.patch.dict(os.environ):
            os.environ.pop("ENABLE_DATAGOUV_PUBLICATION", None)
            publish_datagouv_all.run()

        chain_mock.assert_not_called()
        notify_tech_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv non lancée",
            details=[
                ("Variable", "ENABLE_DATAGOUV_PUBLICATION"),
                ("Valeur", "non définie"),
            ],
        )
        self.assertIsInstance(notify_tech_mock.call_args.kwargs["details"][0][1], Code)

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "false"})
    @mock.patch("batid.tasks.chain")
    @mock.patch("batid.tasks.notify_tech")
    def test_false_flag_launches_nothing(self, notify_tech_mock, chain_mock):
        """
        Input: publish_datagouv_all with ENABLE_DATAGOUV_PUBLICATION="false".
        Expected: no chain queued, one alert "Publication data.gouv non lancée"
        with the value "false" as Code.
        """
        publish_datagouv_all.run()

        chain_mock.assert_not_called()
        notify_tech_mock.assert_called_once_with(
            level=TchapLevel.ALERT,
            title="Publication data.gouv non lancée",
            details=[
                ("Variable", "ENABLE_DATAGOUV_PUBLICATION"),
                ("Valeur", "false"),
            ],
        )
        self.assertIsInstance(notify_tech_mock.call_args.kwargs["details"][1][1], Code)

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch("batid.tasks.chain")
    @mock.patch("batid.tasks.notify_tech")
    def test_enabled_flag_launches_the_chain(self, notify_tech_mock, chain_mock):
        """
        Input: publish_datagouv_all with ENABLE_DATAGOUV_PUBLICATION="true", an
        empty data directory.
        Expected: the chain is queued once and the launch message is unchanged.
        """
        data_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, data_dir)

        with mock.patch(
            "batid.services.data_gouv_publication.WRITABLE_DATA_DIR", data_dir
        ):
            publish_datagouv_all.run()

        chain_mock.return_value.assert_called_once_with()
        notify_tech_mock.assert_called_once_with(
            level=TchapLevel.LAUNCH,
            title="Publication data.gouv lancée",
            details=[("Zones", "tous les départements et le fichier national")],
        )

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch("batid.tasks.chain")
    @mock.patch("batid.tasks.notify_tech")
    def test_new_run_removes_previous_run_directories(
        self, notify_tech_mock, chain_mock
    ):
        """
        Input: a data directory holding the run directory of a chain stopped a week
        ago before its national file (with a department archive in it), the run
        directory of a national still running (modified just now), a department
        working directory and a file; publish_datagouv_all launched.
        Expected: the week-old run directory is removed before the chain is queued;
        the running one, the working directory and the file are kept.
        """
        data_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, data_dir)
        old_run_dir = os.path.join(data_dir, "datagouvfr_run_stopped")
        os.makedirs(old_run_dir)
        with open(os.path.join(old_run_dir, "RNB_75.csv.zip"), "wb") as f:
            f.write(b"zip")
        week_ago = (datetime.now() - timedelta(days=7)).timestamp()
        os.utime(old_run_dir, (week_ago, week_ago))
        running_run_dir = os.path.join(data_dir, "datagouvfr_run_running")
        os.makedirs(running_run_dir)
        with open(os.path.join(running_run_dir, "RNB_75.csv.zip"), "wb") as f:
            f.write(b"zip")
        os.makedirs(os.path.join(data_dir, "datagouvfr_publication_75_2026-11-21"))
        with open(os.path.join(data_dir, "other.csv"), "wb") as f:
            f.write(b"csv")

        def queue_chain(*tasks):
            # the chain starts the new run: the old directory must be gone by then
            self.assertFalse(os.path.exists(old_run_dir))
            return mock.DEFAULT

        chain_mock.side_effect = queue_chain

        with mock.patch(
            "batid.services.data_gouv_publication.WRITABLE_DATA_DIR", data_dir
        ):
            publish_datagouv_all.run()

        chain_mock.return_value.assert_called_once_with()
        self.assertEqual(
            sorted(os.listdir(data_dir)),
            [
                "datagouvfr_publication_75_2026-11-21",
                "datagouvfr_run_running",
                "other.csv",
            ],
        )
        self.assertEqual(os.listdir(running_run_dir), ["RNB_75.csv.zip"])

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch(
        "batid.tasks.remove_previous_run_directories",
        side_effect=PermissionError("run directory not removable"),
    )
    @mock.patch("batid.tasks.chain")
    @mock.patch("batid.tasks.notify_tech")
    def test_failing_cleanup_sends_no_launch_message(
        self, notify_tech_mock, chain_mock, remove_mock
    ):
        """
        Input: publish_datagouv_all with publication enabled, the removal of the
        previous run directories raising.
        Expected: the error is raised, no chain queued and no "Publication data.gouv
        lancée" message sent (the task retry would otherwise send it twice).
        """
        with self.assertRaisesRegex(PermissionError, "run directory not removable"):
            publish_datagouv_all.run()

        chain_mock.assert_not_called()
        notify_tech_mock.assert_not_called()


def zip_records(archive_path):
    with ZipFile(archive_path) as archive:
        (entry_name,) = archive.namelist()
        with archive.open(entry_name) as entry:
            return list(csv_records(entry))


def record_id(record):
    return record.partition(b";")[0]


def point_building(*, rnb_id, wkt, **fields):
    geom = GEOSGeometry(wkt, srid=4326)
    return Building.objects.create(
        rnb_id=rnb_id, shape=geom, point=geom, status="constructed", **fields
    )


class TestNationalArchive(TransactionTestCase):
    """
    The national file assembled from the department archives of a run.

    TransactionTestCase: the national snapshot sets its isolation level, which
    Postgres refuses inside the transaction wrapping a TestCase. Departments are
    limited to 75 and 93, two adjacent squares sharing the edge x = 3.
    NATIONAL_FRESH_MARGIN is 0: with the real 24 h every building created by a test
    would be exported fresh and the department files never read. The data directory
    is a container directory: the bind-mounted one of the dev stack stores whole
    seconds mtimes, which would date the department exports up to 1 s too early.
    """

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.data_dir)
        for patcher in (
            mock.patch(
                "batid.services.data_gouv_publication.WRITABLE_DATA_DIR",
                self.data_dir,
            ),
            mock.patch(
                "batid.services.data_gouv_publication.dpts_list",
                return_value=["75", "93"],
            ),
            mock.patch(
                "batid.services.data_gouv_publication.NATIONAL_FRESH_MARGIN",
                timedelta(0),
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.run_id = uuid.uuid4().hex
        self.run_dir = run_directory(self.run_id)

        Department_subdivided.objects.create(
            code="75",
            name="Paris",
            shape=GEOSGeometry("POLYGON((2 48, 3 48, 3 49, 2 49, 2 48))", srid=4326),
        )
        Department_subdivided.objects.create(
            code="93",
            name="Seine-Saint-Denis",
            shape=GEOSGeometry("POLYGON((3 48, 4 48, 4 49, 3 49, 3 48))", srid=4326),
        )
        point_building(rnb_id="BDG-IN-75", wkt="POINT(2.5 48.5)")
        point_building(rnb_id="BDG-IN-93", wkt="POINT(3.5 48.5)")

    def export_department(self, dept):
        """Build the department archive of the run, as its task does."""
        path, _, _ = build_department_archive(dept=dept, run_dir=self.run_dir)
        return zip_records(path)

    def build_national(self):
        directory = create_directory("nat")
        archive_path, _, _ = create_national_archive(
            directory=directory, run_id=self.run_id
        )
        return archive_path

    def national_ids(self, archive_path):
        records = zip_records(archive_path)
        self.assertTrue(records[0].startswith(b"rnb_id;point;"))
        return sorted(record_id(record) for record in records[1:])

    def test_border_building_appears_once(self):
        """
        Input: a building on the edge shared by 75 and 93, both departments exported.
        Expected: it is in both department files and once in the national file,
        next to the two buildings inside the departments.
        """
        point_building(rnb_id="BDG-BORDER", wkt="POINT(3 48.5)")

        self.assertIn(b"BDG-BORDER", map(record_id, self.export_department("75")))
        self.assertIn(b"BDG-BORDER", map(record_id, self.export_department("93")))

        self.assertEqual(
            self.national_ids(self.build_national()),
            [b"BDG-BORDER", b"BDG-IN-75", b"BDG-IN-93"],
        )

    def test_building_outside_every_department_is_exported(self):
        """
        Input: a building in no department polygon, both departments exported.
        Expected: it is in the national file.
        """
        point_building(rnb_id="BDG-OUTSIDE", wkt="POINT(5 48.5)")
        self.export_department("75")
        self.export_department("93")

        self.assertEqual(
            self.national_ids(self.build_national()),
            [b"BDG-IN-75", b"BDG-IN-93", b"BDG-OUTSIDE"],
        )

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch("batid.tasks.notify_tech_or_log")
    @mock.patch("batid.tasks.notify_tech")
    @mock.patch("batid.services.data_gouv_publication.upload_to_s3")
    def test_department_failing_again_blocks_the_national_file(
        self, upload_mock, notify_tech_mock, summary_mock
    ):
        """
        Input: 75 exported, 93 missing and its rebuild raising.
        Expected: create_national_archive raises naming 93; through the national task
        with publication enabled, nothing is uploaded and one Tchap failure for zone
        "nat" names 93.
        """
        self.export_department("75")

        with mock.patch(
            "batid.services.data_gouv_publication.create_archive",
            side_effect=Exception("copy failed"),
        ):
            with self.assertRaisesRegex(NationalArchiveError, "Department 93"):
                self.build_national()

            with self.assertLogs("batid.tasks", level="ERROR"):
                publish_datagouv_national.apply(kwargs={"run_id": self.run_id})

        upload_mock.assert_not_called()
        notify_tech_mock.assert_called_once()
        kwargs = notify_tech_mock.call_args.kwargs
        self.assertEqual(kwargs["level"], TchapLevel.FAILURE)
        self.assertEqual(kwargs["title"], "Échec de la publication data.gouv")
        self.assertEqual(kwargs["details"], [("Zone", "nat")])
        self.assertIn("Department 93", kwargs["error"])
        self.assertIn("copy failed", kwargs["error"])

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch(
        "batid.services.data_gouv_publication.publish_on_data_gouv_with_retries"
    )
    @mock.patch("batid.services.data_gouv_publication.upload_to_s3")
    def test_missing_department_is_rebuilt(self, upload_mock, publish_mock):
        """
        Input: 75 exported, 93 missing, national published under the run id.
        Expected: 93 is rebuilt for the national file, which holds its building;
        only RNB_nat.csv.zip is uploaded.
        """
        self.export_department("75")
        uploaded = {}

        def capture(archive_path):
            uploaded[os.path.basename(archive_path)] = self.national_ids(archive_path)
            return "https://example.test/RNB_nat.csv.zip"

        upload_mock.side_effect = capture

        self.assertTrue(publish(area="nat", run_id=self.run_id))

        self.assertEqual(uploaded, {"RNB_nat.csv.zip": [b"BDG-IN-75", b"BDG-IN-93"]})

    def test_building_edited_between_two_department_exports(self):
        """
        Input: 75 exported; then building A moves from 75 to 93 and building B of 75
        is deactivated; then 93 exported (A is in both files, B in the 75 one).
        Expected: the national file holds A once, with its new point, and not B.
        """
        point_building(rnb_id="BDG-GONE", wkt="POINT(2.6 48.5)")
        self.export_department("75")
        moved = GEOSGeometry("POINT(3.7 48.6)", srid=4326)
        Building.objects.filter(rnb_id="BDG-IN-75").update(point=moved, shape=moved)
        Building.objects.filter(rnb_id="BDG-GONE").update(is_active=False)
        self.assertIn(b"BDG-IN-75", map(record_id, self.export_department("93")))

        records = zip_records(self.build_national())

        self.assertEqual(
            sorted(map(record_id, records[1:])), [b"BDG-IN-75", b"BDG-IN-93"]
        )
        (moved_record,) = [r for r in records if record_id(r) == b"BDG-IN-75"]
        self.assertIn(b"POINT(3.7 48.6)", moved_record)

    def test_records_are_copied_byte_for_byte(self):
        """
        Input: in 75, a building whose status holds a newline and double quotes (a
        CSV record over two lines) and whose address street holds them too (escaped
        by JSON), and a building with an empty status (empty string) and no plot
        (NULL plots); both departments exported.
        Expected: their national records are byte-equal to their 75 records; the
        national file parses with csv into one header and the 4 expected rows; a
        single entry RNB_nat.csv with mode 0o100644.
        """
        address = Address.objects.create(
            cle_interop="75105_0001_00001", street='rue "du"\nport'
        )
        point_building(
            rnb_id="BDG-QUOTE",
            wkt="POINT(2.4 48.5)",
            addresses_internal_id=[address.internal_id],
        )
        Building.objects.filter(rnb_id="BDG-QUOTE").update(status='built "a"\nb')
        point_building(rnb_id="BDG-EMPTY", wkt="POINT(2.3 48.5)")
        Building.objects.filter(rnb_id="BDG-EMPTY").update(status="")
        dept_75 = {record_id(r): r for r in self.export_department("75")}
        self.export_department("93")

        with self.assertLogs(level="INFO") as logs:
            archive_path = self.build_national()

        # every row comes from the department files, none from the fresh export
        messages = "\n".join(logs.output)
        self.assertIn("0 fresh rows exported", messages)
        self.assertIn("4 department rows copied", messages)
        national = {record_id(r): r for r in zip_records(archive_path)}
        self.assertEqual(national[b"BDG-QUOTE"], dept_75[b"BDG-QUOTE"])
        self.assertEqual(national[b"BDG-QUOTE"].count(b"\n"), 2)
        self.assertEqual(national[b"BDG-EMPTY"], dept_75[b"BDG-EMPTY"])
        self.assertIn(b';"";', national[b"BDG-EMPTY"])
        self.assertTrue(national[b"BDG-EMPTY"].endswith(b";;[]\n"))
        with ZipFile(archive_path) as archive:
            self.assertEqual(archive.namelist(), ["RNB_nat.csv"])
            self.assertEqual(
                archive.getinfo("RNB_nat.csv").external_attr >> 16, 0o100644
            )
            with io.TextIOWrapper(
                archive.open("RNB_nat.csv"), encoding="utf-8", newline=""
            ) as f:
                rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0][0], "rnb_id")
        self.assertEqual(
            sorted(row[0] for row in rows[1:]),
            ["BDG-EMPTY", "BDG-IN-75", "BDG-IN-93", "BDG-QUOTE"],
        )
        (quote_row,) = [row for row in rows if row[0] == "BDG-QUOTE"]
        self.assertEqual(quote_row[3], 'built "a"\nb')
        self.assertEqual(json.loads(quote_row[5])[0]["street"], 'rue "du"\nport')

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch("batid.services.data_gouv_publication.upload_to_s3")
    def test_row_count_mismatch_blocks_the_national_file(self, upload_mock):
        """
        Input: margin of minus one day (no building counts as edited), both
        departments exported, then BDG-IN-75 deactivated.
        Expected: the national publication raises a row count mismatch giving
        2 department rows, 0 fresh rows and 1 active building; nothing uploaded.
        """
        self.export_department("75")
        self.export_department("93")
        Building.objects.filter(rnb_id="BDG-IN-75").update(is_active=False)

        with mock.patch(
            "batid.services.data_gouv_publication.NATIONAL_FRESH_MARGIN",
            timedelta(days=-1),
        ):
            with self.assertRaisesRegex(
                NationalArchiveError,
                "2 department rows \\+ 0 fresh rows, 1 active buildings",
            ):
                publish(area="nat", run_id=self.run_id)

        upload_mock.assert_not_called()

    def test_new_chain_during_the_national_keeps_its_run_directory(self):
        """
        Input: both departments exported, the run directory last modified two days
        ago (a national started long after its departments); a new chain removes the
        idle run directories while the national selects its fresh buildings.
        Expected: the national file is built and holds the buildings of both
        departments.
        """
        self.export_department("75")
        self.export_department("93")
        two_days_ago = (datetime.now() - timedelta(days=2)).timestamp()
        os.utime(self.run_dir, (two_days_ago, two_days_ago))
        real_write_fresh_buildings = data_gouv_publication.write_fresh_buildings

        def new_chain_starts(**kwargs):
            remove_previous_run_directories()
            return real_write_fresh_buildings(**kwargs)

        with mock.patch(
            "batid.services.data_gouv_publication.write_fresh_buildings",
            side_effect=new_chain_starts,
        ):
            archive_path = self.build_national()

        self.assertEqual(self.national_ids(archive_path), [b"BDG-IN-75", b"BDG-IN-93"])

    def test_swapped_buildings_block_the_national_file(self):
        """
        Input: margin of minus one day (no building counts as edited); 75 exported;
        then BDG-IN-75 and BDG-IN-93 swap departments; 93 exported. Both files hold
        BDG-IN-75, none BDG-IN-93: 2 rows for 2 active buildings.
        Expected: the national file is refused despite the matching row count.
        """
        self.export_department("75")
        in_75 = GEOSGeometry("POINT(2.5 48.5)", srid=4326)
        in_93 = GEOSGeometry("POINT(3.5 48.5)", srid=4326)
        Building.objects.filter(rnb_id="BDG-IN-75").update(point=in_93, shape=in_93)
        Building.objects.filter(rnb_id="BDG-IN-93").update(point=in_75, shape=in_75)
        self.assertEqual(
            [record_id(r) for r in self.export_department("93")[1:]], [b"BDG-IN-75"]
        )

        with mock.patch(
            "batid.services.data_gouv_publication.NATIONAL_FRESH_MARGIN",
            timedelta(days=-1),
        ):
            with self.assertRaisesRegex(
                NationalArchiveError,
                "2 department rows \\+ 0 fresh rows, 2 active buildings",
            ):
                self.build_national()

    @mock.patch.dict(os.environ, {"ENABLE_DATAGOUV_PUBLICATION": "true"})
    @mock.patch(
        "batid.services.data_gouv_publication.publish_on_data_gouv_with_retries"
    )
    @mock.patch("batid.services.data_gouv_publication.upload_to_s3")
    def test_national_alone_builds_every_department(self, upload_mock, publish_mock):
        """
        Input: national published without run id (publish_opendata --strate
        country), publication enabled.
        Expected: both departments are built and only RNB_nat.csv.zip is uploaded,
        holding their buildings; nothing is left in the data directory.
        """
        uploaded = {}

        def capture(archive_path):
            uploaded[os.path.basename(archive_path)] = self.national_ids(archive_path)
            return "https://example.test/RNB_nat.csv.zip"

        upload_mock.side_effect = capture

        self.assertTrue(publish(area="nat"))

        self.assertEqual(uploaded, {"RNB_nat.csv.zip": [b"BDG-IN-75", b"BDG-IN-93"]})
        self.assertEqual(os.listdir(self.data_dir), [])

    def test_snapshot_is_repeatable_read(self):
        """
        Input: both departments exported, national built while capturing queries.
        Expected: SET TRANSACTION ISOLATION LEVEL REPEATABLE READ comes right after
        BEGIN (Postgres accepts it only before any other query of the transaction),
        and national_fresh is created after it.
        """
        self.export_department("75")
        self.export_department("93")

        with CaptureQueriesContext(connection) as queries:
            self.build_national()

        sqls = [query["sql"] for query in queries.captured_queries]
        self.assertEqual(
            sqls[:2], ["BEGIN", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"]
        )
        self.assertTrue(
            any("CREATE TEMP TABLE national_fresh" in sql for sql in sqls[2:])
        )
