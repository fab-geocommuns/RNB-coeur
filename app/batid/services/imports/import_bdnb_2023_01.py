import csv

from django.contrib.gis.geos import GEOSGeometry
from datetime import datetime, timezone
from batid.services.source import Source, BufferToCopy


def import_bdnd_2023_01_bdgs(dpt):
    print("## Import BDNB 2023 Q4 buildings")

    src = Source("bdnb_2023_01")
    src.set_param("dpt", dpt)
    file_path = src.find(f"{dpt}_bdgs.csv")

    candidates = []

    with open(file_path, "r") as f:
        print("- list buildings")
        reader = csv.DictReader(f, delimiter=";")

        candidates = []
        for row in list(reader)[:10]:
            geom = GEOSGeometry(row["dummy"])
            candidate = {
                "shape": geom.wkt,
                "source": "bdnb",
                "source_version": "2023.01",
                "is_light": False,
                "is_shape_fictive": row["dummy"],
                "source_id": row["dummy"],
                "address_keys": row["dummy"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                
            }
            candidates.append(candidate)

        buffer = BufferToCopy()
        print(f"- write buffer to {buffer.path}")
        buffer.write_data(candidates)

        cols = candidates[0].keys()



def import_bdnd_2023_01_addresses():
    pass
