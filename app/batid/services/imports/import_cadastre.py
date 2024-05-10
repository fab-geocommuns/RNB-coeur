import json
import os
import random
from datetime import datetime, timezone

import psycopg2
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction, connection

from batid.models import Candidate
from batid.services.imports import building_import_history
from batid.services.source import Source, BufferToCopy


def import_bdtopo(release_date, dpt, bulk_launch_uuid=None):

    source_name = "french_cadastre"

    building_import = building_import_history.insert_building_import(
        source_name, bulk_launch_uuid, dpt
    )

    source = Source(source_name)
    source.set_param("release_date", release_date)
    source.set_param("dpt", dpt)

    with open(source.path, "r") as f:
        data = json.load(f)

        candidates = []

        for feature in data["features"][:10]:
            geom = GEOSGeometry(json.dumps(feature["geometry"]), srid=4326)

            candidates.append(
                {
                    "shape": geom.wkt,
                    "is_light": False,
                    "source": "cadastre",
                    "source_version": release_date,
                    "source_id": None,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "random": random.randint(0, 1000000000),
                }
            )

    buffer = BufferToCopy()
    buffer.write_data(candidates)

    with open(buffer.path, "r") as f:
        with transaction.atomic():
            print("-- transfer buffer to db --")
            try:
                with connection.cursor() as cursor:
                    cursor.copy_from(
                        f,
                        Candidate._meta.db_table,
                        sep=";",
                        columns=candidates[0].keys(),
                    )

                    building_import_history.increment_created_candidates(
                        building_import, len(candidates)
                    )

            except (Exception, psycopg2.DatabaseError) as error:
                raise error

    print("- remove buffer")
    os.remove(buffer.path)
