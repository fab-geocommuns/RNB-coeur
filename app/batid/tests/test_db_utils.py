from io import StringIO
from unittest.mock import patch

import psycopg
from batid.models import Plot
from batid.utils import db as db_utils
from batid.utils.db import copy_from_file
from django.db import connection, transaction
from django.test import TestCase

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


class TestConnectionBinding(TestCase):
    def test_client_side_binding(self):
        """
        Input: current connection.
        Expected: client-side binding, so SET statement_timeout = %s works (a
        server-side bound SET is rejected by PostgreSQL).
        """
        self.assertFalse(connection.features.uses_server_side_binding)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = %s", ["5s"])
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], "5s")
