import os

from django.conf import settings


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
            'filename': 'BATIMENT.shp',
        },
        'bdtopo_buffer': {
            'folder': 'bdtopo',
            'filename': 'bdgs.csv',
        },
        'xp-grenoble': {
            'filename': 'bati-grenoble.geojson'
        }

    }

    def __init__(self, name):

        self.name = name
        self.ref = self.refs[name]

    @property
    def path(self) -> str:

        return f"{self._source_dir}/{self.folder}/{self.filename}"

    @property
    def folder(self) -> str:

        folder = self.name

        if 'folder' in self.ref:
            folder = self.ref['folder']

        return folder

    @property
    def filename(self) -> str:

        return self.ref['filename']





