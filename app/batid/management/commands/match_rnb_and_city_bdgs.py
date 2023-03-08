import concurrent
import json
import os
from pprint import pprint

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from batid.models import Building
from batid.utils.geohelpers import feature_w_geom


# This command analyze a city buildings stock and compare it to the RNB
# The city stock must be in a geojson file made of multiploygons


class Command(BaseCommand):

    TARGET_SRID = 2154
    MIN_AREA = 5

    SAMPLE_SIZE = 10

    def __init__(self):
        super().__init__()

        self.geojson_file = "bati-grenoble.geojson"

        self.stats = {

            "city_stock": {
                # BDG types
                "bdgs": 0,
                "bdgs_types": {},
                "below_min_area": 0,
                "ok_for_matching": 0,

            },
            "comparison": {
                "total": 0,
                "without_intersection": 0,
                "with_one_intersection": 0,
                "with_multiple_intersection": 0
            }


        }

        self.city_bdgs = []

    def handle(self, *args, **options):

        self.__init_city_bdgs()
        self.__calc_city_bdgs_stats()
        self.__compare_city_rnb()

        self.__display_stats()

    def __create_tmp_table(self, cursor):

        print('-- creating tmp table')
        create_q = f"CREATE TEMPORARY TABLE batiment_bdnb (batiment_construction_id varchar(40), geom_cstr geometry(MultiPolygon, {self.TARGET_SRID}))"
        cursor.execute(create_q)

        print('-- populate tmp table')
        insert_q = f"INSERT INTO batiment_bdnb (batiment_construction_id, geom_cstr) SELECT batiment_construction_id, ST_Transform(geom_cstr, {self.TARGET_SRID}) FROM batiment_construction"
        cursor.execute(insert_q)

        print('-- index tmp table')
        create_index_q = "CREATE INDEX batiment_bdnb_geom_cstr_idx ON batiment_bdnb USING GIST (geom_cstr)"
        cursor.execute(create_index_q)

        pass

    def __init_city_bdgs(self):

        # First load raw data
        base = "/usr/src/import_data"
        path = f"{base}/{self.geojson_file}"
        with open(path, 'r') as f:
            data = json.load(f)

            if isinstance(self.SAMPLE_SIZE, int):
                end = self.SAMPLE_SIZE
                print(f">>> Limited sample size: {self.SAMPLE_SIZE}")
            else:
                end = len(data['features'])

            self.city_bdgs = data['features'][0:end]

            print(f">>> Loaded {len(self.city_bdgs)} features")

        # Add geom and area
        print('-- init city bdgs')

        init_count = 0
        features = []
        with concurrent.futures.ProcessPoolExecutor() as executor:
            for feature in executor.map(feature_w_geom, self.city_bdgs, [self.TARGET_SRID] * len(self.city_bdgs)):
                init_count += 1
                print(f"\r{init_count}/{len(self.city_bdgs)}", end="")

                features.append(feature)

        self.city_bdgs = features

        print('')

    def __compare_city_rnb(self):

        with connections['bdnb'].cursor() as cursor:

            self.__create_tmp_table(cursor)

            q = "SELECT * FROM batiment_bdnb b WHERE ST_Intersects(b.geom_cstr, %(geom)s)"
            # q = "SELECT * FROM batiment_construction b WHERE b.batiment_construction_id = %(id)s"

            print('-- matching each city bdg')
            grenoble_bdg_wo_bdnb = 0
            for idx, feature in enumerate(self.city_bdgs):

                print(f"\r{idx + 1}/{len(self.city_bdgs)}", end="")

                if not self.__feature_ok_for_matching(feature):
                    continue

                # We count the total number of queries
                self.stats['comparison']['total'] += 1

                params = {
                    "geom": f"{feature['properties']['geom']}"
                }

                cursor.execute(q, params)
                res = cursor.fetchall()

                if len(res) == 0:
                    self.stats['comparison']['without_intersection'] += 1
                elif len(res) == 1:
                    self.stats['comparison']['with_one_intersection'] += 1
                else:
                    self.stats['comparison']['with_multiple_intersection'] += 1

        pass

    def __calc_city_bdgs_stats(self):

        for idx, feature in enumerate(self.city_bdgs):

            # Total count
            self.stats['city_stock']['bdgs'] += 1

            # Bdg types
            bdg_type = feature['properties']['BATIM_TYPE']
            if bdg_type in self.stats['city_stock']['bdgs_types']:
                self.stats['city_stock']['bdgs_types'][bdg_type] += 1
            else:
                self.stats['city_stock']['bdgs_types'][bdg_type] = 1

            # Geom area
            if not self.__feature_has_min_area(feature):
                self.stats['city_stock']['below_min_area'] += 1

            # Ok for matching
            if self.__feature_ok_for_matching(feature):
                self.stats['city_stock']['ok_for_matching'] += 1


    def __display_stats(self):

        pprint(self.stats)

        pass



    def __feature_ok_for_matching(self, feature) -> bool:

        if not "dur" in feature['properties']['BATIM_TYPE']:
            return False

        if feature['properties']['area'] < self.MIN_AREA:
            return False

        return True

    def __feature_has_min_area(self, feature) -> bool:

        if feature['properties']['area'] < self.MIN_AREA:
            return False

        return True



























