import time

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
        self.focus_on = 992976

        # List of (sig_id, [rnb_id,]) that should be matched
        self.expected_matches = [
            {"id_sig": 961830, "expected": ["N191UHQDSS27"]},
            {"id_sig": 961496, "expected": ["4LM3UE6R5VGF", "MM3NSR1JSX8P"]},
            {"id_sig": 961338, "expected": ["9KREWCETUZNE"]},
            {"id_sig": 961788, "expected": ["11PMNB2RQGE9"]},
            {"id_sig": 962306, "expected": ["58R2XS49VTLY", "ZPSERH5CLGYM"]},
            {"id_sig": 962700, "expected": ["8EYFDEFVQWNN"]},
            {"id_sig": 962912, "expected": ["6CU2N6LDQ4U1"]},
            {"id_sig": 963501, "expected": ["XQRJ2698JFG9", "RZXWARR8WX8F"]},
            {
                "id_sig": 963827,
                "expected": [
                    "P79EWQX4BLSP",
                    "GZ7S935Q3V27",
                    "L4VE8V67LS1J",
                    "3UYGUS3BZV5W",
                    "EYQB3Q67WQCL",
                    "38W3Q5BVWK91",
                ],
            },
            {"id_sig": 963730, "expected": ["WQWQKPZR8UYD"]},
            {"id_sig": 962083, "expected": ["SJHHQAKLU685"]},
            {"id_sig": 963398, "expected": ["TXYJR8XEK11G"]},
            {"id_sig": 964299, "expected": ["S12FCWHPAAWN"]},
            {"id_sig": 964635, "expected": ["3AU3R4W341WL"]},
            {
                "id_sig": 963903,
                "expected": ["MNHRJRCD6VAC", "FPTLX6CCM7Z4", "8JS4FDKY84XB"],
            },
            {"id_sig": 964074, "expected": ["9253DCT1SRQV"]},
            {"id_sig": 961483, "expected": ["LUVRR9HZFWGH"]},
            {"id_sig": 964731, "expected": None},
            {
                "id_sig": 964532,
                "expected": [
                    "7EYRH9NGRPFE",
                    "Y6YDVEGR6UF6",
                    "ZY1TR37B9KDG",
                    "47XV85TYDZ21",
                    "KV6NH2AJXB5H",
                    "MXFNFX4GSJHC",
                    "UNK4F97HSQVS",
                    "75N7JKEPXE8L",
                ],
            },
            {"id_sig": 964252, "expected": ["SFXGD4ZBZUUK", "NQQJXWAB1GP7"]},
            # Those below are positionned on the building. We should always find them.
            {"id_sig": 964561, "expected": ["4SX3GG32Q3AP", "CVTQXZ5MZDC5"]},
            {"id_sig": 964372, "expected": ["8T2CRL1TUWFM"]},
            {"id_sig": 964271, "expected": ["RK4PQBFSX3F8"]},
            {"id_sig": 964483, "expected": ["DH1Q54MY46HF"]},
            {"id_sig": 964186, "expected": ["DYRJ6Z2L1M8H", "T88VBXE7BLU3"]},
            {"id_sig": 963688, "expected": ["KC45PXMKVC8L"]},
            {"id_sig": 963884, "expected": ["TGJF7T7W6ZM2"]},
            {"id_sig": 963441, "expected": ["XDPNWM36MYME"]},
            {"id_sig": 963490, "expected": ["V49L4R9G97UW"]},
            {"id_sig": 963376, "expected": ["HXQJLLB3Y8X3"]},
            {"id_sig": 963242, "expected": ["S5KQ9GL68TVS"]},
            {"id_sig": 963153, "expected": ["MAFFZCYJDNQZ"]},
            {"id_sig": 963490, "expected": ["V49L4R9G97UW"]},
            {"id_sig": 963541, "expected": ["VWMMGPEU6KLK"]},
            {"id_sig": 963575, "expected": ["1D6P85NBJP22"]},
            {"id_sig": 963576, "expected": ["1D6P85NBJP22"]},
            {"id_sig": 963587, "expected": ["1CAANK7M4G52"]},
            {"id_sig": 963203, "expected": ["MBSA4CBTF5BA"]},
            {"id_sig": 963136, "expected": ["CLZYBD6P65ZC"]},
            {"id_sig": 963970, "expected": ["EJG89PH5VJ95"]},
            # Those below are the one in the xlsx file (no point)
            {
                "id_sig": 1068370,
                "expected": [],
                "note": "The building is not in the RNB. Why ? This is the one at 45.43535336243443, 5.979235698580166",
            },
            {
                "id_sig": 1068798,
                "expected": ["CEDDH6T64FKJ"],
                "note": "Le point donné est un ancien point qui devrait être considéré comme détruit.. Le supermarché est tout neuf.",
            },
            {"id_sig": 1068799, "expected": ["UCVCA89PV936"]},
            {
                "id_sig": 1068800,
                "expected": ["762LVKM5U2VB", "VBA7GD1ZMDDN"],
                "note": "Ecole",
            },
            {"id_sig": 1068801, "expected": ["Z73WECWCKLJB"], "note": "Piscine"},
            {
                "id_sig": 1068802,
                "expected": [],
                "note": "Batiment absent du RNB. Hotel tout neuf.",
            },
            {
                "id_sig": 992969,
                "expected": ["LGWUELNCM6S4"],
                "note": "Nouvelle salle polyvalente",
            },
            {"id_sig": 992970, "expected": ["SFW6UADDYC7Z"], "note": "Gite"},
            {"id_sig": 992971, "expected": ["9QL9HTWKDA19"], "note": "micro creche"},
            {
                "id_sig": 992974,
                "expected": [
                    "4KV72YBBC5TW",
                    "WMNU13FX7PAP",
                    "J2LMCXREB19S",
                    "L78CDZ51XLY6",
                    "H2LBDC3C985G",
                ],
                "note": "Abbaye loin de la ville",
            },
            {"id_sig": 992975, "expected": ["NS5DDH2167TD"], "note": "école privée"},
            {
                "id_sig": 992976,
                "expected": ["ME21JNV7Y1YX"],
                "note": "bacchus plaza resturant",
            },
            {
                "id_sig": 992977,
                "expected": [
                    "77GZSW9LZQAK",
                    "ETY3ZE6RFRBZ",
                    "8N99ZEUU3DN2",
                    "5GP1RPXMR6GN",
                    "5GP1RPXMR6GN",
                    "7YFJDHPY6WV9",
                    "YEHD7YUBJHZR",
                ],
            },
            {
                "id_sig": 992979,
                "expected": ["1X479J1UKP1R"],
                "note": "centre hebergement",
            },
            {"id_sig": 992980, "expected": ["KLY7ND23HFVW"], "note": "micro crèche"},
            {"id_sig": 992981, "expected": ["7B3GZ5WF6QC1"]},
            {
                "id_sig": 992983,
                "expected": ["NHE62T5XUQQ2", "3FP7LD3XZ1PR", "8DKHCUVBQ6ZC"],
            },
            {"id_sig": 992985, "expected": ["683F7L5TQ1YM"]},
            {"id_sig": 992986, "expected": ["P283MQTR4R7E"], "note": "nouvelle ecole"},
            {"id_sig": 992987, "expected": ["TQ19V5CYR63N"], "note": "CE Caterpillar"},
            {
                "id_sig": 992988,
                "expected": ["NTS5T1EB97Q2"],
                "note": "salle de reception",
            },
            {
                "id_sig": 992990,
                "expected": ["TK8D7SSLJ652"],
                "note": "institut medico educatif georges bonneton",
            },
            {"id_sig": 992991, "expected": ["88EMEDG4S5N4", "9LLFMQKAHDC4"]},
            {
                "id_sig": 992992,
                "expected": ["NLYRNMF4VX7E"],
                "note": "gare pour train touristique",
            },
            {
                "id_sig": 992993,
                "expected": ["VJQNN3XS3357"],
                "note": "nouvelle salle polyvalente du collège",
            },
            {
                "id_sig": 992994,
                "expected": ["VJQNN3XS3357"],
                "note": "nouvelle batiment enseigment du collège",
            },
            {
                "id_sig": 992996,
                "expected": ["HWS8T59DGM7Z", "LMLATD7TK8P1"],
                "note": "mc do",
            },
            {
                "id_sig": 992998,
                "expected": ["9Q9K4GJELCC2"],
                "note": "chalet des glacies - pas visible sur sateliette",
            },
            {
                "id_sig": 992999,
                "expected": ["KRFCRHFVKHQN"],
                "note": "nouvelle salle polyvalente",
            },
            {
                "id_sig": 993000,
                "expected": ["SM5GSPS3X3MU"],
                "note": "centre de loisir",
            },
            {"id_sig": 993001, "expected": ["69YU1WPPYNK6"]},
            # {"id_sig": 993002, "expected": []},
            # {"id_sig": 993003, "expected": []},
            # {"id_sig": 993004, "expected": []},
            # {"id_sig": 993005, "expected": []},
            # {"id_sig": 993006, "expected": []},
            # {"id_sig": 993007, "expected": []},
            # {"id_sig": 993008, "expected": []},
            # {"id_sig": 993009, "expected": []},
            # {"id_sig": 993010, "expected": []},
            # {"id_sig": 993011, "expected": []},
            # {"id_sig": 993012, "expected": []},
            # {"id_sig": 993013, "expected": []},
            # {"id_sig": 993014, "expected": []},
            # {"id_sig": 993015, "expected": []},
            # {"id_sig": 993016, "expected": []},
            # {"id_sig": 993018, "expected": []},
            # {"id_sig": 993019, "expected": []},
            # {"id_sig": 993020, "expected": []},
            # {"id_sig": 993021, "expected": []},
            # {"id_sig": 993024, "expected": []},
            # {"id_sig": 993025, "expected": []},
            # {"id_sig": 993026, "expected": []},
            # {"id_sig": 993027, "expected": []},
            # {"id_sig": 993028, "expected": []},
            # {"id_sig": 993029, "expected": []},
            # {"id_sig": 1068803, "expected": []},
            # {"id_sig": 1068804, "expected": []},
            # {"id_sig": 1068805, "expected": []},
            # {"id_sig": 1068806, "expected": []},
            # {"id_sig": 1068807, "expected": []},
            # {"id_sig": 1068808, "expected": []},
            # {"id_sig": 1068809, "expected": []},
            # {"id_sig": 1068810, "expected": []},
            # {"id_sig": 1068811, "expected": []},
            # {"id_sig": 1068812, "expected": []},
            # {"id_sig": 1068813, "expected": []},
            # {"id_sig": 1068814, "expected": []},
            # {"id_sig": 1068815, "expected": []},
            # {"id_sig": 1068816, "expected": []},
            # {"id_sig": 1068817, "expected": []},
            # {"id_sig": 1068818, "expected": []},
            # {"id_sig": 1068819, "expected": []},
            # {"id_sig": 1068820, "expected": []},
            # {"id_sig": 1068821, "expected": []},
            # {"id_sig": 1068822, "expected": []},
            # {"id_sig": 1068823, "expected": []},
            # {"id_sig": 1068824, "expected": []},
            # {"id_sig": 1068825, "expected": []},
            # {"id_sig": 1068826, "expected": []},
            # {"id_sig": 1068827, "expected": []},
            # {"id_sig": 1068828, "expected": []},
            # {"id_sig": 1068829, "expected": []},
            # {"id_sig": 1068830, "expected": []},
            # {"id_sig": 1068831, "expected": []},
            # {"id_sig": 1068832, "expected": []},
            # {"id_sig": 1068833, "expected": []},
            # {"id_sig": 1068834, "expected": []},
            # {"id_sig": 1068835, "expected": []},
            # {"id_sig": 1068836, "expected": []},
            # {"id_sig": 1068837, "expected": []},
            # {"id_sig": 1068838, "expected": []},
            # {"id_sig": 1068839, "expected": []},
            # {"id_sig": 1068840, "expected": []},
            # {"id_sig": 1068841, "expected": []},
            # {"id_sig": 1068842, "expected": []},
            # {"id_sig": 1068843, "expected": []},
            # {"id_sig": 1068844, "expected": []},
            # {"id_sig": 1068845, "expected": []},
            # {"id_sig": 1068846, "expected": []},
            # {"id_sig": 1068847, "expected": []},
            # {"id_sig": 1068848, "expected": []},
            # {"id_sig": 1068849, "expected": []},
            # {"id_sig": 1068850, "expected": []},
            # {"id_sig": 1068851, "expected": []},
            # {"id_sig": 1068852, "expected": []},
            # {"id_sig": 1068853, "expected": []},
            # {"id_sig": 1068854, "expected": []},
            # {"id_sig": 1068855, "expected": []},
            # {"id_sig": 1068856, "expected": []},
            # {"id_sig": 1068857, "expected": []},
            # {"id_sig": 1068858, "expected": []},
            # {"id_sig": 1068859, "expected": []},
            # {"id_sig": 1068860, "expected": []},
            # {"id_sig": 1068861, "expected": []},
            # {"id_sig": 1068862, "expected": []},
            # {"id_sig": 1068863, "expected": []},
            # {"id_sig": 1068867, "expected": []},
            # {"id_sig": 1068868, "expected": []},
            # {"id_sig": 1068869, "expected": []},
            # {"id_sig": 1068870, "expected": []},
            # {"id_sig": 1068871, "expected": []},
            # {"id_sig": 1068872, "expected": []},
            # {"id_sig": 1068873, "expected": []},
            # {"id_sig": 1068874, "expected": []},
            # {"id_sig": 1068875, "expected": []},
            # {"id_sig": 1068876, "expected": []},
            # {"id_sig": 1068877, "expected": []},
            # {"id_sig": 1068878, "expected": []},
            # {"id_sig": 1068879, "expected": []},
            # {"id_sig": 1068880, "expected": []},
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
        return [test["id_sig"] for test in self.expected_matches]

    def __attach_expected_results(self):
        checked_ids = self.__get_checked_ids()

        for idx, row in enumerate(self.shp_data):
            # If the row is not in the test set, we skip it
            if row["id_sig"] not in checked_ids:
                continue

            # We get the expected results
            expected_results = [
                test["expected"]
                for test in self.expected_matches
                if test["id_sig"] == row["id_sig"]
            ][0]

            self.shp_data[idx]["expected_results"] = expected_results
            self.shp_data[idx][
                "correct_result"
            ] = False  # We assume the result is wrong
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
        # We wait 1 second the ease on Nominatim API
        time.sleep(1)

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
                s.set_params(
                    point=point, address=address, name=feature["properties"]["TOPONYME"]
                )
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
