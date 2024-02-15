import csv
from pprint import pprint

from django.core.management.base import BaseCommand

from batid.services.guess_bdg_new import guess_all
from batid.utils.misc import is_float


class Command(BaseCommand):
    raw_data_path = (
        "notebooks/rapprochements/enseignement_superieur/data/bat_rnb_mesr_complet.csv"
    )
    # work_file_path = "notebooks/rapprochements/dataES/results/results.json"

    def handle(self, *args, **options):
        rows = []

        with open(self.raw_data_path, "r") as file:
            reader = csv.DictReader(file, delimiter=";")

            for row in list(reader)[:10]:
                if row["clef"] == "67FaBFy52D743.299552,5.370533":
                    rows.append(_row_to_guess_params(row))

        results = guess_all(rows)

        for guess in results:
            print("-----")

            pprint(guess)
            if guess["match"]:
                pprint(guess["match"].rnb_id)


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
