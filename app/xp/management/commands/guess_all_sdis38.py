import json
import time
from pprint import pprint

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
import fiona

from batid.services.guess_bdg import BuildingGuess
from batid.services.source import Source


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Add a boolean to reset all guesses
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all guesses",
        )

    def handle(self, *args, **options):
        raw_filename = "erp_geolocalises_20112020.json"
        raw_src = Source("xp-sdis", {"folder": "xp-sdis", "filename": raw_filename})

        if options["reset"]:
            print("resetting all guesses")
            with open(raw_src.path) as f:
                raw_data = json.load(f)

            for idx, row in enumerate(raw_data):
                raw_data[idx]["guess_done"] = False
                raw_data[idx]["guess_matches"] = []

            with open(raw_src.path, "w") as f:
                json.dump(raw_data, f, indent=2)

        with open(raw_src.path) as f:
            raw_data = json.load(f)

        for idx, row in enumerate(raw_data):
            print(f"{idx + 1} / {len(raw_data)}")

            if row["guess_done"]:
                print("already done, skip")
                continue

            print("guessing...")

            time.sleep(0.750)

            guess = BuildingGuess()

            # Point
            point = None
            if row["point"] is not None:
                point = Point(row["point"][1], row["point"][0], srid=4326)

            # Address
            address = f"{row['num_voie']} {row['adresse']}, {row['code_postal']} {row['commune']}"

            # Name
            name = row["toponyme"]

            params = {
                "point": point,
                "address": address,
                "name": name,
            }

            guess.set_params(**params)
            qs = guess.get_queryset()

            matches = []
            for bdg in qs:
                match = {
                    "rnb_id": bdg.rnb_id,
                    "rel_score": getattr(bdg, "score", None),
                    "abs_score": getattr(bdg, "abs_score", None),
                    "sub_scores": {},
                }

                for sub_score in guess.scores.keys():
                    match["sub_scores"][sub_score] = getattr(bdg, sub_score, None)

                matches.append(match)

            raw_data[idx]["guess_done"] = True
            raw_data[idx]["guess_matches"] = matches

            if idx % 100 == 0:
                print("intermediate saving ...")
                with open(raw_src.path, "w") as f:
                    json.dump(raw_data, f, indent=2)

        with open(raw_src.path, "w") as f:
            print("final saving ...")
            json.dump(raw_data, f, indent=2)
