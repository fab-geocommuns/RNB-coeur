import csv
import gzip
import logging
import os
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from typing import Callable

import nanoid
import py7zr
import requests
from batid.services.replayable_task import ReplayableTask
from celery import current_task, states

from app.settings import WRITABLE_DATA_DIR

logger = logging.getLogger(__name__)


def source_data_directory() -> str:
    directory_name = "source_data"
    directory_path = os.path.join(WRITABLE_DATA_DIR, directory_name)
    os.makedirs(directory_path, exist_ok=True)
    return directory_path


# A task replayed by Celery may rewrite a file that the next task of its chain is
# reading. Writing aside then renaming keeps the reader on the previous, complete file
# instead of a truncated one.
def _write_file_atomically(*, path: str, content: bytes) -> None:
    tmp_path = f"{path}.{nanoid.generate(size=10)}.tmp"
    try:
        with open(tmp_path, "wb") as file:
            file.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        _remove_path(tmp_path)
        raise


def remove_after_task_success(path: str) -> None:
    """Remove a consumed source file or folder. Inside a ReplayableTask, wait until
    the task success is stored (see remove_paths_of_successful_task): a task killed
    before is redelivered and needs the file again, one killed after is skipped as
    already successful. Anywhere else, remove it now: a task that loops over
    departments must not keep every extracted folder until its end."""
    # current_task is a proxy: isinstance sees the running task, if any
    if (
        not isinstance(current_task, ReplayableTask)
        or current_task.request.called_directly
    ):
        _remove_path(path)
        return
    # the Celery request accepts any attribute; it lives until the task ends
    paths = getattr(current_task.request, "paths_to_remove", [])
    setattr(current_task.request, "paths_to_remove", [*paths, path])


def remove_paths_of_successful_task(*, request, state: str) -> None:
    if state != states.SUCCESS:
        return
    for path in getattr(request, "paths_to_remove", []):
        _remove_path(path)


def _remove_path(path: str) -> None:
    # Already removed by another run of the same task: the goal is reached.
    if not os.path.lexists(path):
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def _raise_unless_not_found(error: OSError) -> None:
    if not isinstance(error, FileNotFoundError):
        raise error


def delete_files_older_than(*, root_dir: str, cutoff: float) -> int:
    """Delete the files and the empty directories under root_dir last modified or
    created before cutoff (epoch seconds). root_dir itself is kept. Returns the number
    of deleted files."""
    # Extraction keeps the archive mtime, so ctime is what tells a fresh file apart.
    # A fresh empty directory may be filled by a running extraction: kept too.
    deleted_count = 0
    for dir_path, dir_names, file_names in os.walk(
        root_dir, topdown=False, onerror=_raise_unless_not_found
    ):
        for file_name in file_names:
            file_path = os.path.join(dir_path, file_name)
            try:
                stat = os.lstat(file_path)
                if max(stat.st_mtime, stat.st_ctime) < cutoff:
                    os.remove(file_path)
                    deleted_count += 1
            except FileNotFoundError:
                # A running import task may remove its own files meanwhile.
                continue

        if dir_path == root_dir:
            continue
        try:
            stat = os.lstat(dir_path)
            if not os.listdir(dir_path) and max(stat.st_mtime, stat.st_ctime) < cutoff:
                os.rmdir(dir_path)
        except FileNotFoundError:
            continue

    logger.info(
        "Deleted %s files older than %s in %s",
        deleted_count,
        datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),
        root_dir,
    )
    return deleted_count


class Source:
    _dl_dir = source_data_directory()

    # Must be prefixed with a dot

    archive_exts = [".7z", ".tar.gz", ".gz", ".zip"]

    def __init__(self, name, custom_ref=None):
        self.name = name

        if isinstance(custom_ref, dict):
            self.ref = custom_ref
        else:
            self.refs = self.default_ref()
            self.ref = self.refs.get(name, {})

        self.create_abs_dir()

    def default_ref(self) -> dict:
        return {
            "arcep": {
                "folder": "arcep",
                "url": "https://rnb-open.s3.fr-par.scw.cloud/arcep/arcep_reports_latlng.csv",
                "filename": "arcep_reports_latlng.csv",
            },
            "plot": {
                "folder": "plots",
                "url": "https://cadastre.data.gouv.fr/data/etalab-cadastre/{{date}}/geojson/departements/{{dpt}}/cadastre-{{dpt}}-parcelles.json.gz",
                "filename": "cadastre-{{dpt}}-parcelles.json",
            },
            "bdnb_7_buffer": {
                "folder": "bdnb_7",
                "filename": "buffer.csv",
            },
            "bdtopo": {
                "url": "https://data.geopf.fr/telechargement/download/BDTOPO/BDTOPO_3-5_TOUSTHEMES_GPKG_{{projection}}_D{{dpt}}_{{date}}/BDTOPO_3-5_TOUSTHEMES_GPKG_{{projection}}_D{{dpt}}_{{date}}.7z",
                "filename": "BDT_3-5_GPKG_{{projection}}_D{{dpt}}-ED{{date}}.gpkg",
            },
            "bdnb_2023_01": {
                "url": "https://rnb-open.s3.fr-par.scw.cloud/bdnb_2023_01/{{dpt}}.zip"
            },
            "insee-cog-commune": {
                "url": "https://api.insee.fr/metadonnees/V1/geo/communes",
                "folder": "insee_cog",
                "filename": "commune_insee.csv",
            },
            "export": {"filename": "export-{{city}}-{{date}}.geojson"},
            "cached_stats": {"filename": "cached_stats.json"},
            "bal": {
                "url": "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv-bal/adresses-{{dpt}}.csv.gz",
                "filename": "bal-{{dpt}}.csv",
            },
            "ban": {
                "url": "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-{{dpt}}.csv.gz",
                "filename": "adresses-{{dpt}}.csv",
            },
            "ban_with_ids": {
                "url": "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv-with-ids/adresses-with-ids-{{dpt}}.csv.gz",
                "filename": "adresses-with-ids-{{dpt}}.csv",
            },
        }

    def set_param(self, p_key, p_val):
        for k in self.ref:
            if isinstance(self.ref[k], str):
                self.ref[k] = self.ref[k].replace("{{" + p_key + "}}", p_val)

    def set_params(self, params):
        for key, value in params.items():
            self.set_param(key, value)

    @property
    def abs_dir(self):
        return f"{self._dl_dir}/{self.folder}/"

    @property
    def dl_path(self):
        return f"{self.abs_dir}{self.dl_filename}"

    @property
    def dl_filename(self):
        if "dl_filename" in self.ref:
            return self.ref["dl_filename"]

        if "url" in self.ref:
            return os.path.basename(self.url)

        return None

    @property
    def path(self) -> str:
        return f"{self.abs_dir}{self.filename}"

    @property
    def folder(self) -> str:
        folder = self.name

        if "folder" in self.ref:
            folder = self.ref["folder"]

        return folder

    @property
    def filename(self) -> str:
        return self.ref["filename"]

    @property
    def url(self):
        return self.ref["url"]

    def create_abs_dir(self):
        os.makedirs(self.abs_dir, exist_ok=True)

    def download(self):
        self.create_abs_dir()

        response = requests.get(self.url, allow_redirects=True)
        response.raise_for_status()

        _write_file_atomically(path=self.dl_path, content=response.content)

    @property
    def is_archive(self):
        filename = self.dl_filename if self.dl_filename is not None else self.filename

        for ext in self.archive_exts:
            # First we check the downloaded file
            if filename.endswith(ext):
                return True

        return False

    @property
    def uncompress_folder(self):
        for ext in self.archive_exts:
            if self.dl_filename.endswith(ext):
                ext_len = len(ext)
                return self.dl_filename[:-ext_len]

        raise Exception(f"Can't uncompress {self.dl_filename}")

    @property
    def uncompress_abs_dir(self):
        return f"{self.abs_dir}{self.uncompress_folder}/"

    def uncompress(self):
        if not self.is_archive:
            return

        if self.dl_filename.endswith(".7z"):
            self.uncompress_7z()
            return

        if self.dl_filename.endswith(".tar.gz"):
            self.uncompress_tar_gz()
            return

        if self.dl_filename.endswith(".gz"):
            self.uncompress_gz()
            return

        if self.dl_filename.endswith(".zip"):
            self.uncompress_zip()
            return

    def uncompress_zip(self):
        with zipfile.ZipFile(self.dl_path, "r") as zip_ref:
            self._extract_atomically(zip_ref.extractall)

    def uncompress_7z(self):
        with py7zr.SevenZipFile(self.dl_path, "r") as archive:
            self._extract_atomically(archive.extractall)

    def uncompress_tar_gz(self):
        with tarfile.open(self.dl_path, "r:gz") as tar:
            self._extract_atomically(tar.extractall)

    def uncompress_gz(self):
        with gzip.open(self.dl_path, "rb") as f_in:
            _write_file_atomically(path=self.path, content=f_in.read())

    def _extract_atomically(self, extract: Callable[[str], None]) -> None:
        # Same reason as _write_file_atomically. Extracted outside abs_dir, so that
        # find() never returns a partially extracted file.
        tmp_dir = os.path.join(self._dl_dir, "extracting", nanoid.generate(size=10))
        # An empty archive creates nothing: the folder must exist anyway
        os.makedirs(tmp_dir)
        try:
            extract(tmp_dir)
        except BaseException:
            _remove_path(tmp_dir)
            raise

        target_dir = self.uncompress_abs_dir.rstrip("/")
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        os.replace(tmp_dir, target_dir)

    def remove_archive(self):
        if not self.is_archive:
            return

        os.remove(self.dl_path)

    def remove_uncompressed_folder(self):
        if self.is_archive:
            remove_after_task_success(self.uncompress_abs_dir)

    def find(self, filename):
        root_dir = self.abs_dir

        for root, dirs, files in os.walk(root_dir):
            if filename in files:
                return f"{root}/{filename}"

        return None


class BufferToCopy(Source):
    def __init__(self):
        uuid = nanoid.generate(size=10)
        name = f"buffer_{uuid}"

        super().__init__(
            name,
            {
                "folder": "buffers_to_copy",
                "filename": f"{name}.csv",
            },
        )

    # write data to a csv file, no header
    def write_data(self, data):
        with open(self.path, "w") as f:
            if isinstance(data[0], list) or isinstance(data[0], tuple):
                writer = csv.writer(
                    f, delimiter=";", doublequote=False, escapechar="\\"
                )
                writer.writerows(data)
                return

            if isinstance(data[0], dict):
                writer = csv.DictWriter(
                    f,
                    fieldnames=data[0].keys(),
                    delimiter=";",
                    doublequote=False,
                    escapechar="\\",
                )
                # writer.writeheader()
                writer.writerows(data)
                return

        raise Exception(
            f"Can't write buffer, data rows must be a list or a dict, {type(data)} given"
        )
