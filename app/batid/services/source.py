import csv
import gzip
import os
import tarfile
import zipfile

import nanoid
import py7zr
import requests


class Source:
    _dl_dir = os.environ.get("DOWNLOAD_DIR")

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
            "plot": {
                "folder": "plots",
                "url": "https://cadastre.data.gouv.fr/data/etalab-cadastre/2023-07-01/geojson/departements/{{dpt}}/cadastre-{{dpt}}-parcelles.json.gz",
                "filename": "cadastre-{{dpt}}-parcelles.json",
            },
            "bdnb_7_buffer": {
                "folder": "bdnb_7",
                "filename": "buffer.csv",
            },
            # 2022 december
            # "bdtopo_2022_12": {
            #     "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_224$BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2022-12-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2022-12-15.7z",
            #     "filename": "BATIMENT.shp",
            # },
            # ######
            # For BD TOPO we use the edition name (eg: bdtopo_2023_09) as the source name for continental data. DROM COM source names are suffixed with _{dpt}
            "bdtopo": {
                "url": "https://data.geopf.fr/telechargement/download/BDTOPO/BDTOPO_3-3_TOUSTHEMES_SHP_{{projection}}_D{{dpt}}_{{date}}/BDTOPO_3-3_TOUSTHEMES_SHP_{{projection}}_D{{dpt}}_{{date}}.7z"
            },
            "bdtopo_2023_09": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            # Special case for 03, download url is slightly different
            "bdtopo_2023_09_003": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233-1$BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_971": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D971_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D971_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_972": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D972_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D972_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_973": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_UTM22RGFG95_D973_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_UTM22RGFG95_D973_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_974": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGR92UTM40S_D974_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGR92UTM40S_D974_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_975": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGSPM06U21_D975_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGSPM06U21_D975_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_976": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGM04UTM38S_D976_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGM04UTM38S_D976_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_977": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D977_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D977_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            "bdtopo_2023_09_978": {
                "url": "https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_233$BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D978_2023-09-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_RGAF09UTM20_D978_2023-09-15.7z",
                "filename": "BATIMENT.shp",
            },
            # BDNB 7.2 is not used anymore
            # "bdnb_7": {
            #     "url": "https://open-data.s3.fr-par.scw.cloud/bdnb_v072/v072_{{dpt}}/open_data_v072_{{dpt}}_csv.tar.gz",
            # },
            "bdnb_2023_01": {
                "url": "https://rnb-open.s3.fr-par.scw.cloud/bdnb_2023_01/{{dpt}}.zip"
            },
            "insee-cog-commune": {
                "url": "https://api.insee.fr/metadonnees/V1/geo/communes",
                "folder": "insee_cog",
                "filename": "commune_insee.csv",
            },
            "export": {"filename": "export-{{city}}-{{date}}.geojson"},
            "ads-dgfip": {"filename": "{{fname}}"},
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

        # open in binary mode
        with open(self.dl_path, "wb") as file:
            # get request
            response = requests.get(self.url, allow_redirects=True)
            response.raise_for_status()

            # write to file
            file.write(response.content)

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
            zip_ref.extractall(self.uncompress_abs_dir)

    def uncompress_7z(self):
        with py7zr.SevenZipFile(self.dl_path, "r") as archive:
            archive.extractall(self.uncompress_abs_dir)

    def uncompress_tar_gz(self):
        with tarfile.open(self.dl_path, "r:gz") as tar:
            tar.extractall(self.uncompress_abs_dir)

    def uncompress_gz(self):
        with gzip.open(self.dl_path, "rb") as f_in:
            with open(self.path, "wb") as f_out:
                f_out.write(f_in.read())

    def remove_archive(self):
        if not self.is_archive:
            return

        os.remove(self.dl_path)

    def find(self, filename):
        root_dir = self.abs_dir

        if self.is_archive:
            root_dir = self.uncompress_abs_dir

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


def bdtopo_src_params(dpt: str, date: str) -> dict:

    dpt = dpt.zfill(3)
    projection = _bdtopo_dpt_projection(dpt)

    return {
        "dpt": dpt,
        "projection": projection,
        "date": date,
    }


def bdtopo_most_recent_date() -> str:
    return "2023-09-15"


def _bdtopo_dpt_projection(dpt: str) -> str:

    default_proj = "LAMB93"

    projs = {
        "971": "RGAF09UTM20",
        "972": "RGAF09UTM20",
        "973": "UTM22RGFG95",
        "974": "RGR92UTM40S",
        "975": "RGSPM06U21",
        "976": "RGM04UTM38S",
        "977": "RGAF09UTM20",
        "978": "RGAF09UTM20",
    }

    return projs.get(dpt, default_proj)
