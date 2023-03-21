import json
import os
from pprint import pprint

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from batid.models import Candidate
import pandas as pd


class Command(BaseCommand):



    def handle(self, *args, **options):

        # Candidate.objects.all().delete()




































