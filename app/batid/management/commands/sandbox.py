import csv
import json
from pprint import pprint

import fiona
from django.contrib.gis.geos import GEOSGeometry, WKTWriter
from django.core.management.base import BaseCommand

from batid.models import Building, Candidate
from batid.services.candidate import Inspector
from batid.services.closest_bdg import get_closest
from batid.services.source import Source, bdtopo_source_switcher
from batid.services.imports.import_bdtopo import import_bdtopo
from batid.tasks import dl_source
from batid.tests.helpers import create_bdg
from batid.utils.geo import fix_nested_shells


class Command(BaseCommand):
    def handle(self, *args, **options):
        pass
