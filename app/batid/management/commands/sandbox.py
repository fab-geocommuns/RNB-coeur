import csv
import os
from django.core.management.base import BaseCommand

from batid.services.guess_bdg_new import Guesser
from batid.utils.misc import is_float


class Command(BaseCommand):
    data_path = (
        "notebooks/rapprochements/enseignement_superieur/data/bat_rnb_mesr_complet.csv"
    )

    work_file = "notebooks/rapprochements/enseignement_superieur/results/guess.json"

    def handle(self, *args, **options):
        # check if work_file exists
        if not os.path.exists(self.work_file):
            with open(self.data_path, "r") as f:
                print("- creating work file -")

                reader = csv.DictReader(f, delimiter=";")
                data = [_row_to_guess_params(row) for row in reader]

                guesser = Guesser()
                guesser.create_work_file(data, self.work_file)

        # guess
        guesser = Guesser()
        guesser.guess_work_file(self.work_file)


def _row_to_guess_params(row):
    # Address
    address = f"{row['Adresse']}, {row['CP']} {row['Ville']}".strip()

    # Coords
    lat = float(row["lat"]) if is_float(row["lat"]) else None
    lng = float(row["long"]) if is_float(row["long"]) else None

    # Name
    big_place_name = row.get("Etablissement", None)
    bdg_name = row.get("Libellé bât/ter", None)
    name = f"{big_place_name} {bdg_name}".strip()

    return {
        "ext_id": row.get("clef", None),
        "lat": lat,
        "lng": lng,
        "name": name,
        "address": address,
    }
