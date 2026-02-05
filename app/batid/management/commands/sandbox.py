import csv
import time

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from batid.services.imports.import_bal import find_bdg_to_link
from batid.services.source import Source


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        src = Source("bal")
        src.set_params({"dpt": "33"})
        # src.download()
        # src.uncompress()

        found = 0
        total_time = 0
        c = 0

        with open(src.find(src.filename), "r") as f:
            reader = csv.DictReader(f, delimiter=";")

            idx = 0
            for row in reader:

                idx += 1

                if idx % 100 == 0:
                    print(f"Processing row {idx}, found {found} links")

                if idx == 1000:
                    break

                if row["certification_commune"] == "0":
                    continue

                address_point = Point(
                    float(row["long"]),
                    float(row["lat"]),
                    srid=4326,
                )

                start = time.time()
                bdg = find_bdg_to_link(address_point, row["cle_interop"])
                end = time.time()
                total_time += end - start
                c += 1

                if bdg is not None:
                    found += 1
                    print(
                        f"Found link for building {bdg.rnb_id} at address {row['cle_interop']}"
                    )

        print(f"Finished processing, found {found} links")
        print(f"Total time: {total_time}")
        print(f"Average time: {total_time / c}")
