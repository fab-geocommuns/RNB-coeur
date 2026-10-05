"""Tests covering the raw SQL paths affected by the PostgreSQL driver swap (issue #998)."""

import os
from io import StringIO
from unittest.mock import patch

import batid.services.imports.import_bdnb7 as import_bdnb7
import batid.services.imports.import_bdnb_2023_01 as import_bdnb_2023_01
import batid.tests.helpers as helpers
import psycopg
from batid.models import (
    ADS,
    Address,
    Building,
    BuildingADS,
    Candidate,
    Contribution,
    Department_subdivided,
    Plot,
)
from batid.services import ads, contributions
from batid.services.ads import get_cities
from batid.services.candidate import Inspector
from batid.services.data_gouv_publication import (
    cleanup_directory,
    create_csv,
    create_directory,
)
from batid.tests.helpers import (
    coords_to_mp_geom,
    create_bdg,
    create_default_bdg,
    create_grenoble,
    create_paris,
)
from batid.tests.test_data_gouv_publication import (
    get_department_75_geom,
    get_geom_paris,
)
from batid.utils import db as db_utils
from batid.utils.db import copy_from_file
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from freezegun import freeze_time
from rest_framework.test import APITestCase

PARIS_COORDS = [
    [2.349804906833981, 48.85789205519228],
    [2.349701279442314, 48.85786369735885],
    [2.3496535925009994, 48.85777922711969],
    [2.349861764341199, 48.85773095834841],
    [2.3499452164882086, 48.857847406681174],
    [2.349804906833981, 48.85789205519228],
]


class TestGetCitiesByRnbIds(TestCase):
    def test_rnb_ids_only(self):
        """
        Input: one building in Paris, one in Grenoble, one unknown rnb_id.
        Expected: both cities returned ordered by code_insee, one id works,
        empty inputs return [].
        """
        create_paris()
        create_grenoble()
        create_bdg("PARISBDG0001", PARIS_COORDS)
        create_default_bdg("GRENOBLEBDG1")

        cities = get_cities(["GRENOBLEBDG1", "PARISBDG0001", "UNKNOWN00000"], [])
        self.assertEqual([c.code_insee for c in cities], ["38185", "75056"])
        self.assertEqual(
            [c.code_insee for c in get_cities(["GRENOBLEBDG1"], [])], ["38185"]
        )
        self.assertEqual(get_cities([], []), [])


class TestGuessStatusFilter(APITestCase):
    @freeze_time("2025-01-01")
    def test_status_filter(self):
        """
        Input: a constructed and a demolished building at the same place, guess
        by point with status=constructed then constructed,demolished.
        Expected: first call returns the constructed one only, second both.
        """
        coords = [
            [5.721187072129851, 45.18439363812283],
            [5.721094925229238, 45.184330511384644],
            [5.721122483180295, 45.184274061453465],
            [5.721241326846666, 45.18428316628476],
            [5.721187072129851, 45.18439363812283],
        ]
        create_bdg("CONSTRUCTED1", coords)
        create_bdg("DEMOLISHED01", coords)
        Building.objects.filter(rnb_id="DEMOLISHED01").update(status="demolished")

        url = "/api/alpha/buildings/guess/?point=45.184327114924656,5.721176133001023"
        r = self.client.get(url + "&status=constructed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([b["rnb_id"] for b in r.json()], ["CONSTRUCTED1"])

        r = self.client.get(url + "&status=constructed,demolished")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            sorted(b["rnb_id"] for b in r.json()), ["CONSTRUCTED1", "DEMOLISHED01"]
        )


class TestInspectorMatchingStatus(TestCase):
    def test_non_real_status_is_not_a_match(self):
        """
        Input: candidate overlapping a demolished and a constructed building.
        Expected: only the constructed building matches; the candidate shape is
        read back as a geometry (no EWKB bytes parsing error).
        """
        create_bdg("CONSTRUCTED1", PARIS_COORDS)
        create_bdg("DEMOLISHED01", PARIS_COORDS)
        Building.objects.filter(rnb_id="DEMOLISHED01").update(status="demolished")
        Candidate.objects.create(
            shape=coords_to_mp_geom(PARIS_COORDS),
            source="bdnb",
            source_version="7.2",
            source_id="bdnb_1",
            address_keys=[],
            is_light=False,
            created_by={"id": 46, "source": "import"},
        )

        inspector = Inspector()
        inspector.get_candidate()
        self.assertIsNotNone(inspector.candidate)
        self.assertEqual(inspector.candidate.shape.geom_type, "MultiPolygon")
        inspector.get_matching_bdgs()
        self.assertEqual([b.rnb_id for b in inspector.matching_bdgs], ["CONSTRUCTED1"])


class TestExportFormat(TestCase):
    def test_ads_and_contributions_export(self):
        """
        Input: one ADS with one building operation, one contribution.
        Expected: one dict per export with the file number, rnb_id, shape and username
        for the ADS, and the text for the contribution.
        """
        user = User.objects.create_user(username="exporter", email="e@example.com")
        ads_obj = ADS.objects.create(file_number="ADS-1", creator=user)
        BuildingADS.objects.create(
            ads=ads_obj,
            rnb_id="BDG000000001",
            operation="build",
            shape="POINT(2.35 48.85)",
        )
        rows = ads.export_format()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file_number"], "ADS-1")
        self.assertEqual(rows[0]["rnb_id"], "BDG000000001")
        self.assertEqual(rows[0]["shape"], "POINT(2.35 48.85)")
        self.assertEqual(rows[0]["username"], "exporter")

        Contribution.objects.create(rnb_id="BDG000000001", text="hello", user=user)
        rows = contributions.export_format()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "hello")


PLOT_COLUMNS = ("id", "shape", "created_at", "updated_at", "source_version")
COPY_TIMESTAMP = "2026-01-01 00:00:00+00"


class TestCopyFromFile(TestCase):
    @patch.object(db_utils, "COPY_CHUNK_SIZE", 4)
    def test_escaped_delimiter_null_and_unicode(self):
        """
        Input: text COPY file with an escaped delimiter, a NULL (backslash N)
        and non ASCII text, chunk size patched to 4 chars.
        Expected: delimiter kept in the id, a NULL source_version, accents intact.
        """
        ts = COPY_TIMESTAMP
        f = StringIO(
            f"a\\;b;MULTIPOLYGON EMPTY;{ts};{ts};\\N\n"
            f"p2;MULTIPOLYGON EMPTY;{ts};{ts};été\n"
        )
        with connection.cursor() as cursor:
            copy_from_file(
                cursor=cursor,
                file=f,
                table=Plot._meta.db_table,
                columns=PLOT_COLUMNS,
                sep=";",
            )
            cursor.execute("select id, source_version from batid_plot order by id")
            rows = cursor.fetchall()
        self.assertEqual(rows, [("a;b", None), ("p2", "été")])


class TestCopyFromFileConnectionMode(TestCase):
    def test_blocking_during_copy_and_restored_after_success(self):
        """
        Input: a successful copy_from_file through the Django connection.
        Expected: the libpq connection is blocking while the file is read, its
        mode is back to the initial one afterwards, and it still runs queries.
        """
        with connection.cursor() as cursor:
            pgconn = cursor.connection.pgconn
        before = pgconn.nonblocking
        modes_while_reading = []

        class RecordingFile(StringIO):
            def read(self, size=-1):
                modes_while_reading.append(pgconn.nonblocking)
                return super().read(size)

        ts = COPY_TIMESTAMP
        f = RecordingFile(f"p1;MULTIPOLYGON EMPTY;{ts};{ts};v1\n")
        with connection.cursor() as cursor:
            copy_from_file(
                cursor=cursor,
                file=f,
                table=Plot._meta.db_table,
                columns=PLOT_COLUMNS,
                sep=";",
            )
            self.assertEqual(pgconn.nonblocking, before)
            cursor.execute("select count(*) from batid_plot")
            self.assertEqual(cursor.fetchone()[0], 1)
        self.assertEqual(set(modes_while_reading), {0})

    def test_restored_after_mid_stream_error(self):
        """
        Input: copy_from_file whose second row has an invalid timestamp, inside
        an atomic block.
        Expected: psycopg DataError raised, connection mode back to the initial
        one, connection still runs queries.
        """
        with connection.cursor() as cursor:
            pgconn = cursor.connection.pgconn
        before = pgconn.nonblocking
        ts = COPY_TIMESTAMP
        f = StringIO(
            f"p1;MULTIPOLYGON EMPTY;{ts};{ts};v1\n"
            f"p2;MULTIPOLYGON EMPTY;not-a-date;{ts};v2\n"
        )
        with self.assertRaises(psycopg.errors.DataError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    copy_from_file(
                        cursor=cursor,
                        file=f,
                        table=Plot._meta.db_table,
                        columns=PLOT_COLUMNS,
                        sep=";",
                    )
        self.assertEqual(pgconn.nonblocking, before)
        with connection.cursor() as cursor:
            cursor.execute("select 1")
            self.assertEqual(cursor.fetchone()[0], 1)


class TestDriverInvariants(TestCase):
    def test_client_side_binding(self):
        """
        Input: current connection.
        Expected: client-side binding, SET statement_timeout = %s works.
        """
        self.assertFalse(connection.features.uses_server_side_binding)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = %s", ["5s"])
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], "5s")


class TestImportAddressesTwice(TransactionTestCase):
    @patch("batid.services.imports.import_bdnb7.Source.find")
    def test_bdnb7_twice(self, source_mock):
        """
        Input: same address file imported twice.
        Expected: three addresses after each run, no error.
        """
        source_mock.return_value = helpers.fixture_path("adresses_bdnb_7.csv")
        import_bdnb7.import_bdnb7_addresses("33")
        self.assertEqual(Address.objects.count(), 3)
        import_bdnb7.import_bdnb7_addresses("33")
        self.assertEqual(Address.objects.count(), 3)

    @patch("batid.services.imports.import_bdnb_2023_01.Source.find")
    def test_bdnb_2023_twice(self, source_mock):
        """
        Input: same address file imported twice.
        Expected: three addresses after each run, no error.
        """
        source_mock.return_value = helpers.fixture_path("bdnb_2023_01_addresses.csv")
        import_bdnb_2023_01.import_bdnd_2023_01_addresses("38")
        self.assertEqual(Address.objects.count(), 3)
        import_bdnb_2023_01.import_bdnd_2023_01_addresses("38")
        self.assertEqual(Address.objects.count(), 3)


class TestCreateCsvBytes(TestCase):
    def test_non_ascii_street(self):
        """
        Input: building linked to an address on "rue de l'Église".
        Expected: the CSV read in binary mode decodes as UTF-8 and contains
        "Église".
        """
        a = Address.objects.create(
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
            addresses_internal_id=[a.internal_id],
        )
        directory_name = create_directory("75")
        self.addCleanup(cleanup_directory, directory_name)
        create_csv(directory_name, "75")
        path = [
            os.path.join(directory_name, f)
            for f in os.listdir(directory_name)
            if f.endswith(".csv")
        ][0]
        with open(path, "rb") as csv_file:
            raw = csv_file.read()
        self.assertIn("Église".encode("utf-8"), raw)
        raw.decode("utf-8")
