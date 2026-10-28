import gzip
import os
import shutil
import tempfile
import zipfile
from unittest import mock

import batid.tasks  # noqa: F401 connects remove_consumed_source_files
from batid.services.source import Source, remove_after_task_success
from django.test import SimpleTestCase

from app.celery import app as celery_app


@celery_app.task(name="batid.tests.test_source.consume_file")
def consume_file(path: str, fail: bool) -> bool:
    remove_after_task_success(path)
    if fail:
        raise RuntimeError("task failed")
    return os.path.exists(path)


class TestRemoveAfterTaskSuccess(SimpleTestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp()
        os.close(handle)
        self.addCleanup(self._remove_if_left)

    def _remove_if_left(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_task_success_removes_the_file_after_storing_it(self):
        """
        Input: a task that consumes a file and succeeds.
        Expected: the file still exists while the task runs, it is removed once
        the task is over.
        """
        result = consume_file.apply(args=[self.path, False])

        self.assertTrue(result.get())
        self.assertFalse(os.path.exists(self.path))

    def test_task_failure_keeps_the_file(self):
        """
        Input: a task that consumes a file and fails.
        Expected: the file is kept for the retry.
        """
        result = consume_file.apply(args=[self.path, True])

        self.assertEqual(result.state, "FAILURE")
        self.assertTrue(os.path.exists(self.path))

    def test_outside_a_task_removes_now(self):
        """
        Input: a call outside a Celery task, then a second one on the same path.
        Expected: the file is removed at once; the second call does nothing.
        """
        remove_after_task_success(self.path)
        self.assertFalse(os.path.exists(self.path))

        remove_after_task_success(self.path)


class TestRewriteKeepsOpenReader(SimpleTestCase):
    """A replayed dl_source rewrites the file the next task of its chain may be
    reading: the reader must keep reading the previous, complete file."""

    def setUp(self):
        self.dl_dir = tempfile.mkdtemp()
        patcher = mock.patch.object(Source, "_dl_dir", self.dl_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.dl_dir)

    def _write_archive(self, *, src: Source, content: bytes) -> None:
        if src.dl_filename.endswith(".zip"):
            with zipfile.ZipFile(src.dl_path, "w") as archive:
                archive.writestr(src.filename, content)
            return
        with gzip.open(src.dl_path, "wb") as archive:
            archive.write(content)

    def _assert_reader_keeps_old_file(self, dl_filename: str) -> None:
        src = Source(
            "test", {"folder": "test", "dl_filename": dl_filename, "filename": "a.csv"}
        )
        # Larger than the read buffer (128 KiB since Python 3.14): the reader must
        # go back to the disk after its first line
        old_content = b"".join(f"old{i}\n".encode() for i in range(200_000))
        self._write_archive(src=src, content=old_content)
        src.uncompress()

        with open(src.find(src.filename), "rb") as reader:
            first_line = reader.readline()

            self._write_archive(src=src, content=b"new\n")
            src.uncompress()

            self.assertEqual(first_line + reader.read(), old_content)

        with open(src.find(src.filename), "rb") as new_file:
            self.assertEqual(new_file.read(), b"new\n")

        extracting_dir = os.path.join(self.dl_dir, "extracting")
        if os.path.isdir(extracting_dir):
            self.assertEqual(os.listdir(extracting_dir), [])

    def test_gz(self):
        """
        Input: a.csv decompressed from a .gz and opened, then the .gz decompressed
        again with another content.
        Expected: the open reader reads the whole old content, find() returns the new.
        """
        self._assert_reader_keeps_old_file("a.csv.gz")

    def test_zip(self):
        """
        Input: a.csv extracted from a .zip and opened, then the .zip extracted again
        with another content.
        Expected: the open reader reads the whole old content, find() returns the new,
        no leftover in the extracting folder.
        """
        self._assert_reader_keeps_old_file("a.zip")
