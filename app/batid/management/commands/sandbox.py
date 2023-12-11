import csv
import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from batid.list_bdg import list_bdgs
from batid.services.building import add_default_status
from batid.services.guess_bdg import BuildingGuess
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_bdgs
from batid.services.source import Source
from batid.tasks import dl_source

from batid.models import Candidate, Building, BuildingStatus
from batid.services.bdg_status import BuildingStatus as BuildingStatusService


class Command(BaseCommand):
    def handle(self, *args, **options):
        for dpt in ["38", "83", "84", "94"]:
            src = Source("bdnb_2023_01")
            src.set_param("dpt", dpt)

            print(f"## Downloading BDNB {dpt}")
            src.download()
            src.uncompress()
            src.remove_archive()

            print("Reading BDNB")

            file_path = src.find(f"{dpt}_adresses.csv")

            with open(file_path, "r") as f:
                reader = csv.DictReader(f, delimiter=",")

                for row in reader:
                    if len(row["numero"]) > 10:
                        print("numero de rue superieur à 10 caractères", row["numero"])

                    if len(row["rep"]) > 10:
                        print("rep superieur à 10 caractères", row["rep"])
