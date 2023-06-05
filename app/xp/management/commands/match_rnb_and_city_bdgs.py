import concurrent
import json
import os
from pprint import pprint

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from batid.models import Building
import pandas as pd
from xp.management.commands.analyze_xp import Command as SuperCommand


from batid.services.source import Source

from batid.utils.db import dictfetchall


# This command analyze a city buildings stock and compare it to the RNB
# The city stock must be in a geojson file made of multiploygons


class Command(SuperCommand):
    # TARGET_SRID = 2154
    # MIN_AREA = 5
    #
    SAMPLE_SIZE = None
    #
    # MIN_COVER_RATIO = 0.85
    # MAX_HAUSDORFF_DISTANCE = 1.5

    def __init__(self):
        super().__init__()

        self.geojson_file = "bati-grenoble.geojson"

        self.city_bdgs = []

    def handle(self, *args, **options):
        self.__init_city_bdgs()

        self.__compare_city_rnb()

        self.__export_back()

    def __export_back(self):
        rnb_covers = {}

        covers_count = {}

        for idx, feature in enumerate(self.city_bdgs):
            rnb_ids = feature["properties"].get("rnb_ids", [])

            # Create the inverse cover count
            for rnb_id in rnb_ids:
                if rnb_id not in rnb_covers:
                    rnb_covers[rnb_id] = []
                rnb_covers[rnb_id].append(feature["properties"]["BATIM_ID"])

            # Clean up the feature
            del self.city_bdgs[idx]["properties"]["geom"]
            del self.city_bdgs[idx]["properties"]["area"]

        for idx, feature in enumerate(self.city_bdgs):
            rnb_ids = feature["properties"].get("rnb_ids", [])

            if len(rnb_ids) == 0:
                cover_type = "no_match"

            elif len(rnb_ids) == 1:
                rnb_id = rnb_ids[0]

                if len(rnb_covers[rnb_id]) == 1:
                    cover_type = "one_rnb_one_grenoble"
                elif len(rnb_covers[rnb_id]) > 1:
                    cover_type = "one_rnb_many_grenoble"

            elif len(rnb_ids) > 1:
                for rnb_id in rnb_ids:
                    if len(rnb_covers[rnb_id]) == 1:
                        cover_type = "many_rnb_one_grenoble"
                    elif len(rnb_covers[rnb_id]) > 1:
                        cover_type = "many_rnb_many_grenoble"
                        break

            self.city_bdgs[idx]["properties"]["match_type"] = cover_type

            covers_count[cover_type] = covers_count.get(cover_type, 0) + 1

            source = Source("xp-grenoble-export")

        f_collection = {"type": "FeatureCollection", "features": self.city_bdgs}

        with open(source.path, "w") as f:
            json.dump(f_collection, f)

        pprint(covers_count)

    def __compare_city_rnb(self):
        with connections["default"].cursor() as cursor:
            # Requêtes de match
            q = (
                "SELECT b.rnb_id as rnb_id "
                "FROM batid_building b "
                "WHERE ST_Intersects(b.shape, %(geom)s) "
                "AND ("
                "ST_Area(ST_Intersection(b.shape, %(geom)s)) / %(f_area)s >= %(min_cover_ratio)s "
                "OR ST_Area(ST_Intersection(b.shape, %(geom)s)) / ST_Area(b.shape) >= %(min_cover_ratio)s "
                "OR ST_HausdorffDistance(b.shape, %(geom)s) <= %(max_hausdorff)s"
                ")"
            )
            # liste des batiments RNB qui recouvrent le bâtiment de la ville

            stats = []

            print("-- matching")

            rnb_covers = {}

            for idx, feature in enumerate(self.city_bdgs):
                print(f"\r{idx + 1}/{len(self.city_bdgs)}", end="")

                if not self.__feature_ok_for_matching(feature):
                    continue

                params = {
                    "geom": f"{feature['properties']['geom']}",
                    "f_area": feature["properties"]["area"],
                    "min_cover_ratio": self.MIN_COVER_RATIO,
                    "max_hausdorff": self.MAX_HAUSDORFF_DISTANCE,
                }

                res = dictfetchall(cursor, q, params)

                rnb_ids = [r["rnb_id"] for r in res]
                self.city_bdgs[idx]["properties"]["rnb_ids"] = rnb_ids

                # Analyze
                stats.append(
                    {
                        "matches_len": len(res),
                        "area": feature["properties"]["area"],
                        "valid": feature["properties"]["BATIM_VALID"],
                        "created_at": feature["properties"]["BATIM_DATECRE"]
                        if feature["properties"]["BATIM_DATECRE"]
                        else "VIDE",
                        "removed_at": feature["properties"]["BATIM_DATESUPP"]
                        if feature["properties"]["BATIM_DATESUPP"]
                        else "VIDE",
                    }
                )

                # print(' ')
                # print(feature['properties']['BATIM_DATECRE'])

            df_all = pd.DataFrame(stats)
            df_all_len = len(df_all)
            df_nomatch = df_all[df_all["matches_len"] == 0]
            df_nomatch_len = len(df_nomatch)

            print("-----")
            print("### Description des correspondances ###")
            print(df_all["matches_len"].describe())
            print("## Nb de correspondance RNB par batiment de Grenoble")
            print(df_all["matches_len"].value_counts().sort_index())
            print(df_all["matches_len"].value_counts(normalize=True).sort_index())

            print("-----")
            print(
                "### Comparaison stock total VS no match selon critères BATIM_VALID ###"
            )

            valid_all_count = df_all.groupby("valid")["valid"].count()
            valid_all_percent = valid_all_count / df_all_len * 100

            valid_nomatch_count = df_nomatch.groupby("valid")["valid"].count()
            valid_nomatch_percent = valid_nomatch_count / df_nomatch_len * 100

            v_compare = pd.concat(
                [
                    valid_all_count,
                    valid_all_percent,
                    valid_nomatch_count,
                    valid_nomatch_percent,
                ],
                axis=1,
            )
            v_compare.columns = ["All count", "All %", "No match count", "No match %"]
            v_compare = v_compare.fillna(0)

            print(v_compare)

            print("-----")
            print(
                "### Comparaison stock total VS no match selon critères BATIM_DATECRE ###"
            )
            year_all_size = df_all.groupby(df_all["created_at"].str[:4]).size()
            year_all_percent = year_all_size / df_all_len * 100

            year_nomatch_size = df_nomatch.groupby(df_all["created_at"].str[:4]).size()
            year_nomatch_percent = year_nomatch_size / df_nomatch_len * 100

            year_compare = pd.concat(
                [
                    year_all_size,
                    year_all_percent,
                    year_nomatch_size,
                    year_nomatch_percent,
                ],
                axis=1,
            )
            year_compare.columns = ["All", "All %", "No match", "No match %"]
            year_compare = year_compare.fillna(0)

            print(year_compare)

    def __feature_ok_for_matching(self, feature) -> bool:
        if not "dur" in feature["properties"]["BATIM_TYPE"]:
            return False

        if feature["properties"]["area"] < self.MIN_AREA:
            return False

        return True

    def __feature_has_min_area(self, feature) -> bool:
        if feature["properties"]["area"] < self.MIN_AREA:
            return False

        return True
