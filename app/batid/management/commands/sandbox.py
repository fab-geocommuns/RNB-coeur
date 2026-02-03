from django.core.management.base import BaseCommand
from batid.services.source import Source
from django.contrib.gis.geos import Point
from batid.models import Building, Plot
from batid.services.bdg_status import BuildingStatus
from django.contrib.gis.db.models.functions import Area, Intersection
from django.db.models import F
import csv


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        src = Source("bal")
        src.set_params({"dpt": "33"})
        # src.download()
        # src.uncompress()

        found = 0

        with open(src.find(src.filename), "r") as f:
            reader = csv.DictReader(f, delimiter=";")

            for row in reader:

                if row["certification_commune"] == "0":
                    continue

                address_point = Point(
                    float(row["long"]),
                    float(row["lat"]),
                    srid=4326,
                )

                address_point.transform(2154)
                buffer = address_point.buffer(3)
                buffer.transform(4326)

                plots = Plot.objects.filter(shape__intersects=buffer)

                if plots.count() != 1:
                    continue

                plot = plots.first()

                bdgs = Building.objects.filter(
                    shape__coveredby=plot.shape,
                    is_active=True,
                    status__in=BuildingStatus.REAL_BUILDINGS_STATUS,
                ).exclude(shape__intersects=buffer)

                if bdgs.count() == 1:

                    found = found + 1

                    address_point.transform(4326)

                    lat_lng = f"{address_point.y},{address_point.x}"

                    print(
                        f"Linking {row['cle_interop']}, {lat_lng} to BDG {bdgs.first().rnb_id}"
                    )
                    print(f"Plot {plot.id}")

                    if found >= 10:
                        break
