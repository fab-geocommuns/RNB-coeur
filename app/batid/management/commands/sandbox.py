import json
import os
from pprint import pprint

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from batid.models import Building


class Command(BaseCommand):

    def __init__(self):
        super().__init__()

        self.geojson_file = "bati-grenoble.geojson"

        self.stats = {

            "city_stock": {
                # BDG types
                "bdgs": 0,
                "bdgs_types": {},

            },
            "comparison": {
                "total": 0,
                "with_intersection": 0,
                "without_intersection": 0,
            }


        }

        self.city_bdgs = []

    def handle(self, *args, **options):

        # Building.objects.all().delete()

        self.__init_city_bdgs()
        self.__calc_city_bdgs_stats()
        self.__compare_city_rnb()

        self.__display_stats()

    def __create_tmp_table(self, cursor):

        print('-- creating tmp table')
        create_q = "CREATE TEMPORARY TABLE batiment_bdnb_4326 (batiment_construction_id varchar(40), geom_cstr geometry(MultiPolygon, 4326))"
        cursor.execute(create_q)

        print('-- populate tmp table')
        insert_q = "INSERT INTO batiment_bdnb_4326 (batiment_construction_id, geom_cstr) SELECT batiment_construction_id, ST_Transform(geom_cstr, 4326) FROM batiment_construction"
        cursor.execute(insert_q)

        print('-- index tmp table')
        create_index_q = "CREATE INDEX batiment_bdnb_4326_geom_cstr_idx ON batiment_bdnb_4326 USING GIST (geom_cstr)"
        cursor.execute(create_index_q)

        pass

    def __init_city_bdgs(self):

        base = "/usr/src/import_data"

        path = f"{base}/{self.geojson_file}"

        with open(path, 'r') as f:
            data = json.load(f)
            self.city_bdgs = data['features']

        pass

    def __compare_city_rnb(self):

        with connections['bdnb'].cursor() as cursor:

            self.__create_tmp_table(cursor)

            q = "SELECT * FROM batiment_bdnb_4326 b WHERE ST_Intersects(b.geom_cstr, %(geom)s)"
            # q = "SELECT * FROM batiment_construction b WHERE b.batiment_construction_id = %(id)s"

            grenoble_bdg_wo_bdnb = 0
            for feature in self.city_bdgs:

                if not "dur" in feature['properties']['BATIM_TYPE']:
                    continue

                # We count the total number of queries
                self.stats['comparison']['total'] += 1


                grenoble_bdg_geom = GEOSGeometry(json.dumps(feature['geometry']))
                params = {
                    "geom": f"{grenoble_bdg_geom}"
                }

                cursor.execute(q, params)
                res = cursor.fetchall()

                if len(res) == 0:
                    self.stats['comparison']['without_intersection'] += 1
                else:
                    self.stats['comparison']['with_intersection'] += 1

        pass

    def __calc_city_bdgs_stats(self):

        for feature in self.city_bdgs:

            # Total count
            self.stats['city_stock']['bdgs'] += 1

            # Bdg types
            bdg_type = feature['properties']['BATIM_TYPE']
            if bdg_type in self.stats['city_stock']['bdgs_types']:
                self.stats['city_stock']['bdgs_types'][bdg_type] += 1
            else:
                self.stats['city_stock']['bdgs_types'][bdg_type] = 1

        pass

    def __display_stats(self):

        pprint(self.stats)

        pass



























