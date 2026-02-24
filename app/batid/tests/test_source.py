import csv
import os
import shutil

from django.test import override_settings
from django.test import SimpleTestCase

from batid.services.source import BufferToCopy
from batid.services.source import Source
from batid.services.source import source_data_directory


class TestSourceDataDirectory(SimpleTestCase):
    def test_creates_source_data_dir_under_writable_data_dir(self):
        """Verify that source_data_directory() creates a 'source_data' subdirectory
        under WRITABLE_DATA_DIR and returns its path."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(WRITABLE_DATA_DIR=tmp):
                result = source_data_directory()

                expected = os.path.join(tmp, "source_data")
                self.assertEqual(result, expected)
                self.assertTrue(os.path.isdir(expected))


class TestSource(SimpleTestCase):
    def setUp(self):
        import tempfile

        self.tmp_dir = tempfile.mkdtemp()
        self.custom_ref = {
            "folder": "my_source",
            "filename": "data.csv",
            "url": "https://example.com/data.csv",
        }

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_source(self, name="test", custom_ref=None):
        """Helper to create a Source with _dl_dir pointing to our temp directory."""
        ref = custom_ref or self.custom_ref
        source = Source(name, ref)
        # Override class-level _dl_dir to use our temp directory
        source._dl_dir = self.tmp_dir
        # Recreate the folder now that _dl_dir changed
        source.create_abs_dir()
        return source

    def test_init_creates_folder(self):
        """Verify that instantiating a Source creates its folder on disk."""
        source = self._make_source()

        self.assertTrue(os.path.isdir(source.abs_dir))

    def test_paths(self):
        """Verify that abs_dir, path, dl_path, and dl_filename return
        correctly constructed paths from the source ref."""
        source = self._make_source()

        self.assertEqual(source.abs_dir, f"{self.tmp_dir}/my_source/")
        self.assertEqual(source.path, f"{self.tmp_dir}/my_source/data.csv")
        self.assertEqual(source.dl_filename, "data.csv")
        self.assertEqual(source.dl_path, f"{self.tmp_dir}/my_source/data.csv")

    def test_set_params_replaces_placeholders(self):
        """Verify that set_params() replaces {{dpt}} and {{date}} placeholders
        in all string values of the source ref."""
        ref = {
            "folder": "bdtopo",
            "filename": "bdtopo-{{dpt}}-{{date}}.gpkg",
            "url": "https://example.com/{{dpt}}/{{date}}.7z",
        }
        source = self._make_source(custom_ref=ref)
        source.set_params({"dpt": "75", "date": "2024-01"})

        self.assertEqual(source.filename, "bdtopo-75-2024-01.gpkg")
        self.assertEqual(source.url, "https://example.com/75/2024-01.7z")

    def test_is_archive(self):
        """Verify that is_archive correctly detects archive extensions."""
        for ext, expected in [
            (".7z", True),
            (".tar.gz", True),
            (".gz", True),
            (".zip", True),
            (".csv", False),
        ]:
            ref = {
                "folder": "test",
                "filename": "out.csv",
                "url": f"https://example.com/file{ext}",
            }
            source = self._make_source(custom_ref=ref)
            self.assertEqual(source.is_archive, expected, f"Failed for extension {ext}")

    def test_folder_defaults_to_name(self):
        """Verify that when no 'folder' key is in the ref, the source name is used."""
        ref = {
            "filename": "data.csv",
            "url": "https://example.com/data.csv",
        }
        source = self._make_source(name="my_name", custom_ref=ref)

        self.assertEqual(source.folder, "my_name")


class TestBufferToCopy(SimpleTestCase):
    def setUp(self):
        import tempfile

        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_data_with_lists(self):
        """Verify that BufferToCopy.write_data() writes list-of-lists data
        as semicolon-delimited CSV rows."""
        buf = BufferToCopy()
        buf._dl_dir = self.tmp_dir
        buf.create_abs_dir()

        data = [["a", "b", "c"], ["1", "2", "3"]]
        buf.write_data(data)

        with open(buf.path) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        self.assertEqual(rows, [["a", "b", "c"], ["1", "2", "3"]])

    def test_write_data_with_dicts(self):
        """Verify that BufferToCopy.write_data() writes list-of-dicts data
        as semicolon-delimited CSV rows (no header)."""
        buf = BufferToCopy()
        buf._dl_dir = self.tmp_dir
        buf.create_abs_dir()

        data = [{"col1": "x", "col2": "y"}, {"col1": "a", "col2": "b"}]
        buf.write_data(data)

        with open(buf.path) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        self.assertEqual(rows, [["x", "y"], ["a", "b"]])
