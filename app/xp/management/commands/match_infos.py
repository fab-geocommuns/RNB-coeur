from django.db import connections

from batid.utils.db import dictfetchall
from xp.management.commands.analyze_xp import Command as SuperCommand


# This command analyze a city buildings stock and compare it to the RNB
# The city stock must be in a geojson file made of multiploygons


class Command(SuperCommand):
    TARGET_BATIM_ID = 23215

    def handle(self, *args, **options):
        self.__init_city_bdgs()

        self.__match_infos()

    def __match_infos(self):
        with connections["default"].cursor() as cursor:
            # Requêtes de match
            q = (
                "SELECT b.rnb_id as rnb_id, "
                "ST_HausdorffDistance(b.shape, %(geom)s) as hausdorff, "
                "ST_Area(ST_Intersection(b.shape, %(geom)s)) / %(f_area)s as rnb_cover_ratio, "
                "ST_Area(ST_Intersection(b.shape, %(geom)s)) / ST_Area(b.shape) as city_cover_ratio "
                "FROM batid_building b "
                "WHERE ST_Intersects(b.shape, %(geom)s) "
            )

            for idx, feature in enumerate(self.city_bdgs):
                print(f"\r{idx + 1}/{len(self.city_bdgs)}", end="")

                params = {
                    "geom": f"{feature['properties']['geom']}",
                    "f_area": feature["properties"]["area"],
                }

                res = dictfetchall(cursor, q, params)

                print("-------------")
                print(f"BATIM ID : {feature['properties']['BATIM_ID']}")
                for r in res:
                    print("##")
                    print(f"RNB ID : {r['rnb_id']}")
                    print(f"Haussdorff distance : {r['hausdorff']}")
                    print(f"RNB Cover ratio : {r['rnb_cover_ratio']}")
                    print(f"City Cover ratio : {r['city_cover_ratio']}")
