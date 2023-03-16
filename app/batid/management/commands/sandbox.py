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

        vals = [
            {
                'hd': 2,
                'cover': .75
            },
            {
                'hd': 1.45,
                'cover': .98
            },
            {
                'hd': 3.45,
                'cover': .98
            },
            {
                'hd': 3.45,
                'cover': .99
            },
            {
                'hd': 2,
                'cover': .99
            }

        ]

        df = pd.DataFrame(vals)

        print(df['hd'].value_counts(normalize=True).sort_values())


































