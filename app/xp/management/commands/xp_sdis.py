from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from batid.models import Building
from batid.services.search_bdg import BuildingSearch
from batid.services.source import Source
from pandas import read_excel
import pandas as pd
import fiona


class Command(BaseCommand):
    def __init__(self):
        super().__init__()

        self.xls_sig_ids = set()
        self.shp_sig_ids = set()

        self.shp_data = []

        self.test_only = True
        self.focus_on = 961338

        # List of (sig_id, [rnb_id,]) that should be matched
        self.expected_matches = [
            (961830, ["N191UHQDSS27"]),
            (961496, ["4LM3UE6R5VGF", "MM3NSR1JSX8P"]),
            (961338, ["9KREWCETUZNE"]),
            (961788, ["11PMNB2RQGE9"]),
            (962306, ["58R2XS49VTLY", "ZPSERH5CLGYM"]),
            (962700, ["8EYFDEFVQWNN"]),
            (962912, ["6CU2N6LDQ4U1"]),
            (963501, ["XQRJ2698JFG9", "RZXWARR8WX8F"]),
            (
                963827,
                [
                    "P79EWQX4BLSP",
                    "GZ7S935Q3V27",
                    "L4VE8V67LS1J",
                    "3UYGUS3BZV5W",
                    "EYQB3Q67WQCL",
                    "38W3Q5BVWK91",
                ],
            ),
            (963730, ["WQWQKPZR8UYD"]),
            (962083, ["SJHHQAKLU685"]),
            (963398, ["TXYJR8XEK11G"]),
            (964299, ["S12FCWHPAAWN"]),
            (964635, ["3AU3R4W341WL"]),
            (963903, ["MNHRJRCD6VAC", "FPTLX6CCM7Z4", "8JS4FDKY84XB"]),
            (964074, ["9253DCT1SRQV"]),
            (961483, ["LUVRR9HZFWGH"]),
            (964731, None),
            (
                964532,
                [
                    "7EYRH9NGRPFE",
                    "Y6YDVEGR6UF6",
                    "ZY1TR37B9KDG",
                    "47XV85TYDZ21",
                    "KV6NH2AJXB5H",
                    "MXFNFX4GSJHC",
                    "UNK4F97HSQVS",
                    "75N7JKEPXE8L",
                ],
            ),
            (964252, ["SFXGD4ZBZUUK", "NQQJXWAB1GP7"]),
            # Ci-dessous, ce sont des ERP qui ont été correctement positionnés sur les bâtiments
            # On les ajoute au résultats à vérifier pour être sûr que la complexité qu'on va introduire
            # ne fait pas sortir des cas aussi simples
            (964561, ["4SX3GG32Q3AP", "CVTQXZ5MZDC5"]),
            (964372, ["8T2CRL1TUWFM"]),
            (964271, ["RK4PQBFSX3F8"]),
            (964483, ["DH1Q54MY46HF"]),
            (964186, ["DYRJ6Z2L1M8H", "T88VBXE7BLU3"]),
            (963688, ["KC45PXMKVC8L"]),
            (963884, ["TGJF7T7W6ZM2"]),
            (963441, ["XDPNWM36MYME"]),
            (963490, ["V49L4R9G97UW"]),
            (963376, ["HXQJLLB3Y8X3"]),
            (963242, ["S5KQ9GL68TVS"]),
            (963153, ["MAFFZCYJDNQZ"]),
            (963490, ["V49L4R9G97UW"]),
            (963541, ["VWMMGPEU6KLK"]),
            (963575, ["1D6P85NBJP22"]),
            (963576, ["1D6P85NBJP22"]),
            (963587, ["1CAANK7M4G52"]),
            (963203, ["MBSA4CBTF5BA"]),
            (963136, ["CLZYBD6P65ZC"]),
            (963970, ["EJG89PH5VJ95"]),
        ]

    def handle(self, *args, **options):
        # self.__handle_xlsx()

        self.__handle_shp()
        self.__evaluate()
        self.__report()

        # self.__count_ids()

    def __evaluate(self):
        self.__attach_expected_results()

        for idx, row in enumerate(self.shp_data):
            if "expected_results" not in row:
                continue

            # The rare cases where we expect to find nothing
            if row["expected_results"] is None and row["rnb_id"] is not None:
                self.shp_data[idx]["errors"].append("empty_result_expected")
                continue

            if isinstance(row["expected_results"], list):
                if row["rnb_id"] is None:
                    self.shp_data[idx]["errors"].append("no_result")
                    continue

                if row["rnb_id"] not in row["expected_results"]:
                    self.shp_data[idx]["errors"].append("wrong_result")
                    continue

    def __report(self):
        # Detail per SIG_ID
        for row in self.shp_data:
            in_test = True if "expected_results" in row else False

            print("----")
            print(f"SIG_ID : {row['id_sig']}")
            print(f"RNB_ID trouvé : {row['rnb_id']}")
            print(f"Dans test : {'Oui' if in_test else 'Non'}")

            if in_test:
                if len(row["errors"]) > 0:
                    self.stdout.write(self.style.ERROR(f"Wrong result"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Correct result"))

                print(f"Best Score : {row['best_score']}")
                print(f"Used scores : {row['used_scores']}")

                print(f"Expected results : {row['expected_results']}")
                print(f"Errors : {row['errors']}")

                if self.focus_on is not None:
                    print("Matches :")
                    for match in row["matches"]:
                        expected = (
                            True if match.rnb_id in row["expected_results"] else False
                        )
                        match_str = f"  - {match.rnb_id} : {match.score} {' -> Expected' if expected else ''}"

                        if expected:
                            self.stdout.write(self.style.SUCCESS(match_str))
                        else:
                            self.stdout.write(match_str)

                        for subscore in row["used_scores"]:
                            print(f"    - {subscore} : {getattr(match, subscore)}")

        print("------------TESTS ONLY RESULTS --------------")

        # Count of correct results
        correct_len = len(
            [
                row
                for row in self.shp_data
                if "errors" in row and len(row["errors"]) == 0
            ]
        )
        print(f"Correct results : {correct_len}")

        # Count of incorrect results
        incorrect_len = len(
            [row for row in self.shp_data if "errors" in row and len(row["errors"]) > 0]
        )
        print(f"Incorrect results : {incorrect_len}")

    def __get_checked_ids(self):
        return [id for id, _ in self.expected_matches]

    def __attach_expected_results(self):
        checked_ids = self.__get_checked_ids()

        for idx, row in enumerate(self.shp_data):
            # If the row is not in the test set, we skip it
            if row["id_sig"] not in checked_ids:
                continue

            # We get the expected results
            expected_results = [
                rnb_ids
                for sig_id, rnb_ids in self.expected_matches
                if sig_id == row["id_sig"]
            ][0]

            self.shp_data[idx]["expected_results"] = expected_results
            self.shp_data[idx][
                "correct_result"
            ] = False  # We assume the result iqs wrong
            self.shp_data[idx]["errors"] = []

    def __count_ids(self):
        print(f"XLS ids : {len(self.xls_sig_ids)}")
        print(f"Shapefile ids : {len(self.shp_sig_ids)}")

        # Count how many sig ids are shared between the xls and the shp
        shared_ids = self.xls_sig_ids.intersection(self.shp_sig_ids)
        print(f"Shared ids : {len(shared_ids)}")

    def __handle_xlsx(self):
        df = self.xls_df()

        # Get all sig ids from the xlsx
        data_dict = df.to_dict(orient="records")
        self.xls_sig_ids = set([d["ID_SIG"] for d in data_dict])

    def xls_df(self):
        filename = "20230623_ERP_non_geolocalises.xlsx"

        src = Source(
            "xp-sdis",
            {
                "folder": "xp-sdis",
                "filename": filename,
            },
        )

        return read_excel(src.find(filename), sheet_name="23-06-2023")

    def __handle_shp(self):
        print("--- Shapefile ---")

        filename = "erp_geolocalises_20112020.shp"

        src = Source("xp-sdis", {"folder": "xp-sdis", "filename": filename})

        # The row ids we want to test
        tested_ids = self.__get_checked_ids()

        with fiona.open(src.find(filename)) as f:
            c = 1

            # Count the total number of rows
            if self.focus_on:
                total = 1
            elif self.test_only:
                total = len(tested_ids)
            else:
                total = len(f)

            for feature in f:
                # ####################################################
                # We may filter on specific rows (for testing purpose)

                if self.focus_on is not None:
                    # Focused id is top priority
                    if feature["properties"]["ID_SIG"] != self.focus_on:
                        continue
                elif self.test_only:
                    # If not focus on, we may filter on test_only
                    if feature["properties"]["ID_SIG"] not in tested_ids:
                        continue

                print(f"\r{c}/{total}", end="")
                c += 1

                point = None
                if feature["geometry"] is not None:
                    point = Point(feature["geometry"]["coordinates"])
                    point.srid = 2154

                adress_items = [
                    feature["properties"]["NUM_VOIE"],
                    feature["properties"]["ADRESSE"],
                    str(feature["properties"]["CODE_POSTA"]),
                    feature["properties"]["COMMUNE"],
                ]
                adress_items = [i for i in adress_items if i is not None]
                address = " ".join(adress_items)

                s = BuildingSearch()
                s.set_params(point=point, address=address)
                matches = s.get_queryset()[:10]

                rnb_id = None
                score = None
                used_scores = []
                if len(matches) > 0:
                    rnb_id = matches[0].rnb_id
                    score = matches[0].score
                    used_scores = s.scores.keys()

                row = {
                    "toponyme": feature["properties"]["TOPONYME"],
                    "num_voie": feature["properties"]["NUM_VOIE"],
                    "adresse": feature["properties"]["ADRESSE"],
                    "code_postal": feature["properties"]["CODE_POSTA"],
                    "commune": feature["properties"]["COMMUNE"],
                    "type_adres": feature["properties"]["TYPE_ADRES"],
                    "point": point,
                    "id_sig": feature["properties"]["ID_SIG"],
                    "rnb_id": rnb_id,
                    "best_score": score,
                    "used_scores": used_scores,
                    "matches": matches,
                }

                # First we collect the sig_id from the shp to check if some are shared witht the xls file
                self.shp_sig_ids.add(row["id_sig"])

                # We add the row to the df data
                self.shp_data.append(row)

        # self.display_erp_with_rnb_id()

    def display_erp_with_rnb_id(self):
        print("SIG_ID with RNB_ID :")

        for row in self.shp_data:
            if row["rnb_id"] is not None:
                print(f"{row['id_sig']} : {row['rnb_id']}")

    def display_erp_wo_rnb_id(self):
        # How many rows are with one rnb_id ?
        print("SIG_ID without RNB_ID :")
        print([int(row["id_sig"]) for row in self.shp_data if row["rnb_ids"] is None])

    def display_counts(self):
        # Transform data into DF
        df = pd.DataFrame(self.shp_data)

        # How many rows are without point ?
        print(f"Rows without point : {len(df[df['point'].isnull()])}")

        # How many rows are with a rnb_id ?
        print(f"Rows with rnb_id : {len(df[df['rnb_id'].notnull()])}")

        # How many rows are without rnb_id ?
        print(f"Rows without rnb_id : {len(df[df['rnb_id'].isnull()])}")
