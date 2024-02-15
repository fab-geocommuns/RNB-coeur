import csv
import json
from pprint import pprint

import pandas as pd
from django.core.management.base import BaseCommand
from batid.services.guess_bdg_new import guess_all
from batid.utils.misc import is_float


class Command(BaseCommand):
    work_file_path = "notebooks/rapprochements/dataES/results/results.json"

    def handle(self, *args, **options):
        # self.report()
        self.do_pairing()

    def do_pairing(self):
        with open("notebooks/rapprochements/dataES/data/data-es.csv") as f:
            reader = csv.DictReader(f, delimiter=";")

            rows = []

            for csv_row in list(reader)[:10]:
                params = rowToParams(csv_row)
                if params["ext_id"] == "E001I010040001":
                    rows.append(params)

            guesses = guess_all(rows)
            pprint(guesses)

    def report(self):
        with open(self.work_file_path, "r") as f:
            data = json.load(f)
            data = list(data.values())
            df = pd.json_normalize(data, sep="_")

        # show 10 items with a match_subscores_osm_point_on_bdg = 10
        print(df[df["match_subscores_osm_point_on_bdg"] == 10].head(10))


def rowToParams(row) -> dict:
    address_infos = [
        row["Numéro, type et nom de la voie"],
        row["Code postal"],
        row["Commune Nom"],
    ]
    address_infos = [info for info in address_infos if info is not None]

    return {
        "ext_id": row["Numéro de l'équipement sportif"],
        "name": row["Nom de l'installation sportive"],
        "address": ", ".join(address_infos),
        "lat": float(row["Latitude (WGS84)"])
        if is_float(row["Latitude (WGS84)"])
        else None,
        "lng": float(row["Longitude (WGS84)"])
        if is_float(row["Longitude (WGS84)"])
        else None,
    }


# function to split list in x lists of given size
def _split_list(lst, chunk_size):
    """
    Splits a list into sublists, each containing up to X items.

    Parameters:
    lst (list): The list to be split.
    X (int): The maximum number of items per sublist.

    Returns:
    list of lists: A list of sublists, each containing up to X items.
    """
    if chunk_size <= 0:
        raise ValueError("X must be a positive integer")
    # Use list comprehension to create the sublists
    sublists = [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]
    return sublists
