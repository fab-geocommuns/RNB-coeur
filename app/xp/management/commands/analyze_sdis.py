import json

import pandas as pd
from django.core.management.base import BaseCommand

from batid.services.source import Source


class Command(BaseCommand):
    FILENAME = "erp_geolocalises_20112020.json"

    def handle(self, *args, **options):
        raw_src = Source("xp-sdis", {"folder": "xp-sdis", "filename": self.FILENAME})

        # open json with pandas

        df = pd.read_json(raw_src.path)

        df["confident_guess"] = df["guess_matches"].apply(
            lambda x: (len(x) > 0 and x[0]["rel_score"] >= 0.75)
            or (
                len(x) > 1
                and x[1]["rel_score"] > 0  # We need a second guess to compare
                and x[0]["rel_score"] > 0.15  # We need a quite strong first guess
                and x[0]["rel_score"] / x[1]["rel_score"] > 2.5
            )
            or (len(x) > 0 and x[0]["sub_scores"].get("point_distance", 0) >= 5)
        )

        rows_c = len(df)
        guess_done_c = len(df[df["guess_done"] == True])
        confident_guess_c = len(df[df["confident_guess"] == True])

        # First count rows
        print(f"Number of rows: {rows_c}")

        # Then count rows with guess_done = True
        print(f"Number of rows with guess_done = True: {guess_done_c}")

        # Then count rows with confident_guess = True
        print(f"Number of rows with confident_guess = True: {confident_guess_c}")
        print(
            f"Percentage of confident : {round(confident_guess_c / rows_c, 4) * 100}%"
        )

        print("---------------")
        # Get distribution of abs_score in confident_df, sorted by abs_score
        confident_df = df[df["confident_guess"] == True]
        print("Distribution of abs_score in confident_df")
        print(
            confident_df["guess_matches"]
            .apply(lambda x: round(x[0]["abs_score"], 0) if len(x) > 0 else None)
            .value_counts()
            .sort_index()
        )

        print("---------------")
        print("Count of subscore 'point_distance' >= 5 in confident_df")
        print(
            confident_df["guess_matches"]
            .apply(
                lambda x: (
                    x[0]["sub_scores"].get("point_distance", 0) >= 5
                    if len(x) > 0
                    else False
                )
            )
            .value_counts()
            .sort_index()
        )

        print("---------------")
        print("How rows with point = None ?")
        print(df["point"].apply(lambda x: x is None).value_counts().sort_index())
        print("How rows with confident = True and point = None ?")
        print(
            confident_df["point"].apply(lambda x: x is None).value_counts().sort_index()
        )

        print("---------------")
        # Get distribution of abs_score in unconfident_df
        unconfident_df = df[df["confident_guess"] == False]
        print("Distribution of abs_score in unconfident_df")
        print(
            unconfident_df["guess_matches"]
            .apply(
                lambda x: (
                    round(x[0]["abs_score"], 0)
                    if len(x) > 0 and x[0]["abs_score"] is not None
                    else None
                )
            )
            .value_counts()
            .sort_index()
        )

        print("---------------")
        print("How many rows have point but no 'point_distance' subscore ?")
        with_point_df = df[df["point"].apply(lambda x: x is not None)]
        print(
            with_point_df["guess_matches"]
            .apply(
                lambda x: (
                    "point_distance" in x[0]["sub_scores"] if len(x) > 0 else False
                )
            )
            .value_counts()
            .sort_index()
        )

        with open(raw_src.path, "r") as f:
            rows = json.load(f)
            c = 0
            for row in rows:
                if row["guess_matches"]:
                    if (
                        row["point"] is not None
                        and row["guess_matches"][0]["sub_scores"].get(
                            "point_distance", None
                        )
                        is None
                    ):
                        c += 1
            print("Number of rows with point but not point_distance subscore", c)
