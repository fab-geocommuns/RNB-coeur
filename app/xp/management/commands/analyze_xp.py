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


from batid.services.source import Source

from batid.utils.db import dictfetchall


# This command analyze a city buildings stock and compare it to the RNB
# The city stock must be in a geojson file made of multiploygons


class Command(BaseCommand):
    TARGET_SRID = 2154
    MIN_AREA = 5

    SAMPLE_SIZE = None
    TARGET_BATIM_ID = None

    MIN_COVER_RATIO = 0.75
    MAX_HAUSDORFF_DISTANCE = 1.5

    def __init__(self):
        super().__init__()

    def __init_city_bdgs(self):
        # First load raw data
        source = Source("xp-grenoble")

        with open(source.path, "r") as f:
            data = json.load(f)

            if isinstance(self.SAMPLE_SIZE, int):
                end = self.SAMPLE_SIZE
                print(f">>> Limited sample size: {self.SAMPLE_SIZE}")
            else:
                end = len(data["features"])

            self.city_bdgs = data["features"][0:end]

            # Keep only one id if required
            if isinstance(self.TARGET_BATIM_ID, int):
                self.city_bdgs = [
                    b
                    for b in self.city_bdgs
                    if b["properties"]["BATIM_ID"] == self.TARGET_BATIM_ID
                ]

            print(f">>> Loaded {len(self.city_bdgs)} features")

        # Add geom and area
        print("-- init city bdgs")

        init_count = 0
        features = []
        with concurrent.futures.ProcessPoolExecutor() as executor:
            for feature in executor.map(feature_w_geom, self.city_bdgs):
                init_count += 1
                print(f"\r{init_count}/{len(self.city_bdgs)}", end="")

                features.append(feature)

        self.city_bdgs = features

        print("")


def feature_w_geom(feature: dict) -> dict:
    geom = GEOSGeometry(json.dumps(feature["geometry"]))

    if geom.srid != 4326:
        geom.transform(4326)

    feature["properties"]["geom"] = geom
    feature["properties"]["area"] = geom.area

    return feature
