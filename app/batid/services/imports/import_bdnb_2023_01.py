import csv
import json
import os

import psycopg2
from django.contrib.gis.geos import GEOSGeometry
from datetime import datetime, timezone

from django.db import transaction, connection

from batid.models import Candidate
from batid.services.imports import building_import_history
from batid.services.source import Source, BufferToCopy


def import_bdnd_2023_01_bdgs(dpt):
    print("## Import BDNB 2023 Q4 buildings")

    source_id = "bdnb_2023_01"

    building_import = building_import_history.insert_building_import(source_id, dpt)

    src = Source(source_id)
    src.set_param("dpt", dpt)
    file_path = src.find(f"{dpt}_bdgs.csv")

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
                "created_by": json.dumps(
                    {"source": "import", "id": building_import.id}
                ),
            }
            candidates.append(candidate)

        buffer = BufferToCopy()
        print(f"- write buffer to {buffer.path}")
        buffer.write_data(candidates)

        cols = candidates[0].keys()

        with open(buffer.path, "r") as f:
            with transaction.atomic():
                print("- import buffer")
                try:
                    with connection.cursor() as cursor:
                        cursor.copy_from(
                            f, Candidate._meta.db_table, sep=";", columns=cols
                        )

                    building_import_history.increment_created_candidates(
                        building_import, len(candidates)
                    )
                except (Exception, psycopg2.DatabaseError) as error:
                    raise error

        print("- remove buffer")
        os.remove(buffer.path)


def import_bdnd_2023_01_addresses():
    pass
