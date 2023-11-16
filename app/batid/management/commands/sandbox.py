import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from batid.tests.test_inspector import get_bdnb_data


class Command(BaseCommand):
    def handle(self, *args, **options):
        rows = get_bdnb_data()

        for row in rows:
            print("--")
            print(row["id"])

            mp = GEOSGeometry(json.dumps(row["geometry"]))
            mp.srid = 2154

            mp = mp.transform(4326, clone=True)

            print(mp.json)
