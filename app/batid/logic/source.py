import os
from urllib.parse import urlparse
import py7zr

from django.conf import settings
import requests

class Source:

    _source_dir = settings.SOURCE_DIR

    refs = {
        'bdnb_7_buffer': {
            'folder': 'bdnb_7',
            'filename': 'buffer.csv',
        },
        'bdnb_7_bdg': {
            'folder': 'bdnb_7',
            'filename': 'batiment_construction.csv',
        },
        'bdnb_7_rel_address': {
            'folder': 'bdnb_7',
            'filename': 'rel_batiment_groupe_adresse.csv',
        },
        'bdtopo': {
            'url': 'https://wxs.ign.fr/859x8t863h6a09o9o6fy4v60/telechargement/prepackage/BDTOPOV3-TOUSTHEMES-DEPARTEMENT-PACK_224$BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2022-12-15/file/BDTOPO_3-3_TOUSTHEMES_SHP_LAMB93_D{{dpt}}_2022-12-15.7z',
            'filename': 'BATIMENT.shp',
        },
        'bdtopo_buffer': {
            'folder': 'bdtopo',
            'filename': 'bdgs.csv',
        },
        'xp-grenoble': {
            'filename': 'bati-grenoble.geojson'
        },
        'xp-grenoble-export': {
            'folder': 'xp-grenoble',
            'filename': 'match-rnb-grenoble.geojson'
        },
        'xp-grenoble-export_rnb': {
            'folder': 'xp-grenoble',
            'filename': 'rnb.geojson'
        }

    }

    archive_exts = [
        '.7z',
        '.gz'
    ]

    def __init__(self, name):

        self.name = name
        self.ref = self.refs[name]

    def set_param(self, p_key, p_val):

        for k in self.ref:
            if isinstance(self.ref[k], str):
                self.ref[k] = self.ref[k].replace('{{' + p_key + '}}', p_val)

    @property
    def abs_dir(self):
        return f"{self._source_dir}/{self.folder}/"


    @property
    def dl_path(self):
        return f"{self.abs_dir}{self.dl_filename}"

    @property
    def dl_filename(self):

        if "dl_filename" in self.ref:
            return self.ref['dl_filename']

        return os.path.basename(self.url)

    @property
    def path(self) -> str:
        return f"{self.abs_dir}{self.filename}"



    @property
    def folder(self) -> str:

        folder = self.name

        if 'folder' in self.ref:
            folder = self.ref['folder']

        return folder

    @property
    def filename(self) -> str:

        return self.ref['filename']

    @property
    def url(self):
        return self.ref['url']

    def download(self):

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

        # if not os.path.exists(self.uncompress_abs_dir):
        #     os.makedirs(self.uncompress_abs_dir)

        if self.dl_filename.endswith('.7z'):
            self.uncompress_7z()


        self.delete_archive()

    def delete_archive(self):

        os.remove(self.dl_path)

    def uncompress_7z(self):

        with py7zr.SevenZipFile(self.dl_path, 'r') as archive:
            archive.extractall(self.abs_dir)















