import csv
import json
import pandas as pd

from django.core.management.base import BaseCommand

from batid.services.guess_bdg_new import guess_all, report_format
from batid.utils.misc import is_float


class Command(BaseCommand):
    raw_data_path = (
        "notebooks/rapprochements/enseignement_superieur/data/bat_rnb_mesr_complet.csv"
    )
    report_path = "notebooks/rapprochements/enseignement_superieur/results/results.json"

    def handle(self, *args, **options):
        # self.pair()
        self.read_report()

    def read_report(self):
        with open(self.report_path, "r") as file:
            df = pd.json_normalize(json.load(file), sep="_")

        # print total number of rows
        total = len(df)
        print(f"Total number of rows: {total}")

        # show keys of the dataframe
        print(df.keys())

        # How many have a match not null
        matched = df[df["match_rnb_id"].notnull()]
        matched_total = len(matched)
        print(f"Total number of rows with a match: {matched_total}")

        # List all possible values of match_reason and count rows for each
        print(df["match_reason"].value_counts())

        # To read the rows, we only need somes columns : row_ext_id, row_name, row_lat, row_lng, match_rnb_id
        extract = matched[
            [
                "row_ext_id",
                "row_name",
                "row_lat",
                "row_lng",
                "match_rnb_id",
                "match_reason",
            ]
        ]

        # Get an extract of rows with match_reason = "geocode_name_and_point" and display 25 rows
        print("-- Extract of rows with match_reason = 'geocode_name_and_point' --")
        extract_geocode_name_and_point = extract[
            extract["match_reason"] == "geocode_name_and_point"
        ]
        extract_geocode_name_and_point.head(25)
        # save this extract to a csv file
        extract_geocode_name_and_point.to_csv(
            "notebooks/rapprochements/enseignement_superieur/results/extract_geocode_name_and_point.csv",
            index=False,
        )

        # Get an extract of rows with match_reason = "address_and_point" and display 25 rows
        print("-- Extract of rows with match_reason = 'precise_address_match' --")
        extract_address_and_point = extract[
            extract["match_reason"] == "precise_address_match"
        ]
        extract_address_and_point.head(25)
        # save this extract to a csv file
        extract_address_and_point.to_csv(
            "notebooks/rapprochements/enseignement_superieur/results/extract_address_and_point.csv",
            index=False,
        )

    def pair(self):
        rows = []

        with open(self.raw_data_path, "r") as file:
            reader = csv.DictReader(file, delimiter=";")

            for row in reader:
                rows.append(_row_to_guess_params(row))

        results = guess_all(rows)
        report_data = report_format(results)

        with open(self.report_path, "w") as file:
            json.dump(report_data, file)


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
