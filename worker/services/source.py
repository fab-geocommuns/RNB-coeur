import os
import tarfile
import py7zr
import requests


class Source:
    _dl_dir = os.environ.get("DOWNLOAD_DIR")

    refs = {
        "bdnb_7_buffer": {
            "folder": "bdnb_7",
            "filename": "buffer.csv",
        },
        "bdtopo": {
            "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_224$BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2022-12-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2022-12-15.7z",
            "filename": "BATIMENT.shp",
        },
        "bdnb_7": {
            "url": "https://open-data.s3.fr-par.scw.cloud/bdnb_v072/v072_{{dpt}}/open_data_v072_{{dpt}}_csv.tar.gz",
        },
        "insee-cog-commune": {
            "url": "https://api.insee.fr/metadonnees/V1/geo/communes",
            "folder": "insee_cog",
            "filename": "commune_insee.csv",
        },
        "export": {"filename": "export-{{city}}-{{date}}.geojson"},
    }

    # Must be prefixed with a dot
    archive_exts = [".7z", ".tar.gz"]

    def __init__(self, name, custom_ref=None):
        self.name = name

        if isinstance(custom_ref, dict):
            self.ref = custom_ref
        else:
            self.ref = self.refs[name]

        self.create_abs_dir()

    def set_param(self, p_key, p_val):
        for k in self.ref:
            if isinstance(self.ref[k], str):
                self.ref[k] = self.ref[k].replace("{{" + p_key + "}}", p_val)

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

        return os.path.basename(self.url)

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

        # open in binary mode
        with open(self.dl_path, "wb") as file:
            # get request
            response = requests.get(self.url, allow_redirects=True)
            response.raise_for_status()

            # write to file
            file.write(response.content)

    @property
    def is_archive(self):
        for ext in self.archive_exts:
            if self.dl_filename.endswith(ext):
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

        if self.dl_filename.endswith(".tar.gz"):
            self.uncompress_tar_gz()

        self.remove_archive()

    def uncompress_7z(self):
        with py7zr.SevenZipFile(self.dl_path, "r") as archive:
            archive.extractall(self.abs_dir)

    def uncompress_tar_gz(self):
        with tarfile.open(self.dl_path, "r:gz") as tar:
            tar.extractall(self.uncompress_abs_dir)

    def remove_archive(self):
        os.remove(self.dl_path)

    def find(self, filename):
        root_dir = self.abs_dir

        if self.is_archive:
            root_dir = self.uncompress_abs_dir

        for root, dirs, files in os.walk(root_dir):
            if filename in files:
                return f"{root}/{filename}"

        return None
