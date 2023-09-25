import csv
import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand

from batid.models import Address, Candidate, Building
from batid.services.candidate import Inspector
from batid.services.imports.import_bdnb7 import (
    import_bdnb7_addresses,
    import_bdnb7_bdgs,
)
from batid.services.imports.import_bdtopo import import_bdtopo
from batid.services.source import Source


class Command(BaseCommand):
    def handle(self, *args, **options):
        src = Source("bdnb_7")
        src.set_param("dpt", "44")

        with open(src.find("adresse.csv"), "r") as f:
            print("- list addresses")
            reader = csv.DictReader(f, delimiter=",")

            for row in list(reader):
                if len(row["rep"]) > 5:
                    print("rep is too long")
                    print(row["rep"])

                if len(row["code_postal"]) > 5:
                    print("code_postal is too long")
                    print(row["code_postal"])

                if len(row["code_commune_insee"]) > 5:
                    print("code_commune_insee is too long")
                    print(row["code_commune_insee"])
