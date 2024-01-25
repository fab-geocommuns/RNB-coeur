import csv
import json
from pprint import pprint

import fiona
from django.contrib.gis.geos import GEOSGeometry, WKTWriter
from django.core.management.base import BaseCommand
from shapely.ops import transform
from shapely.geometry import shape

from batid.models import Building, Candidate
from batid.services.candidate import Inspector
from batid.services.source import Source, bdtopo_source_switcher
from batid.services.imports.import_bdtopo import import_bdtopo
from batid.tasks import dl_source
from batid.utils.geo import fix_nested_shells


class Command(BaseCommand):
    def handle(self, *args, **options):
        dpt = "976"
        bdtopo_edition = "bdtopo_2023_09"

        source_name = bdtopo_source_switcher(bdtopo_edition, dpt)

        print(source_name)

        src = Source(source_name)
        src.set_param("dpt", dpt)

        print(f"-- downloading {src.url}")
