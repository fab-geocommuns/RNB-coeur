from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from batid.models import Building
from batid.services.source import Source
from pandas import read_excel
import pandas as pd
import fiona


class Command(BaseCommand):
    def handle(self, *args, **options):
        # self.__analyze_xlsx()
        self.__analyze_shape_file()

    def __analyze_xlsx(self):
        filename = "20230623_ERP_non_geolocalises.xlsx"

        src = Source(
            "xp-sdis",
            {
                "folder": "xp-sdis",
                "filename": filename,
            },
        )

        data = read_excel(src.find(filename), sheet_name="23-06-2023").to_dict(
            orient="records"
        )

    def __analyze_shape_file(self):
        filename = "erp_geolocalises_20112020.shp"

        src = Source("xp-sdis", {"folder": "xp-sdis", "filename": filename})

        analyze = []

        with fiona.open(src.find(filename)) as f:
            for feature in f[:10]:
                point = Point(feature["geometry"]["coordinates"])
                point.srid = 2154

                row = {
                    "toponyme": feature["properties"]["TOPONYME"],
                    "num_voie": feature["properties"]["NUM_VOIE"],
                    "adresse": feature["properties"]["ADRESSE"],
                    "code_postal": feature["properties"]["CODE_POSTA"],
                    "commune": feature["properties"]["COMMUNE"],
                    "type_adres": feature["properties"]["TYPE_ADRES"],
                    "point": point,
                }

                b = Building.objects.filter(shape__intersects=point).first()

                intersect = None
                if b:
                    intersect = b.rnb_id

                analyze.append({"intersect": intersect, **row})

        # Analyze data to check how many buildings are intersected
        df = pd.DataFrame(analyze)
        print(df)
