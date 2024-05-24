import csv
import json
import os
import random
from datetime import datetime
from datetime import timezone
from warnings import warn

import psycopg2
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.db import transaction
from psycopg2.extras import execute_values

from batid.models import Address
from batid.models import Candidate
from batid.services.imports import building_import_history
from batid.services.source import BufferToCopy
from batid.services.source import Source
from batid.utils.db import list_to_pgarray


def import_bdnb7_bdgs(dpt, bulk_launch_uuid=None):
    warn(
        "BDNB 7 is not used anymore. We use a more recent version of BDNB.",
        DeprecationWarning,
    )
    print(f"## Import BDNB 7 buildings in dpt {dpt}")

    source_id = "bdnb_7"

    # insert a record in the table BuildingImport
    building_import = building_import_history.insert_building_import(
        source_id, bulk_launch_uuid, dpt
    )

    src = Source(source_id)
    src.set_param("dpt", dpt)

    groups_addresses = _get_groups_addresses_from_files(dpt)

    candidates = []

    with open(src.find("batiment_construction.csv"), "r") as f:
        print("- list buildings")
        reader = csv.DictReader(f, delimiter=",")

        for row in list(reader):
            geom = GEOSGeometry(row["WKT"], srid=2154).transform(4326, clone=True)
            if row["fictive_geom_cstr"] == "1":
                geom = geom.point_on_surface

            candidate = {
                "shape": geom.wkt,
                "source": "bdnb",
                "source_version": "7.2",
                "is_light": False,
                "source_id": row["batiment_construction_id"],
                "address_keys": list_to_pgarray(
                    groups_addresses.get(row["batiment_groupe_id"], [])
                ),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_by": json.dumps(
                    {"source": "import", "id": building_import.id}
                ),
                "random": random.randint(0, 1000000000),
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
                    cursor.copy_from(f, Candidate._meta.db_table, sep=";", columns=cols)

                building_import_history.increment_created_candidates(
                    building_import, len(candidates)
                )
            except (Exception, psycopg2.DatabaseError) as error:
                raise error

    print("- remove buffer")
    os.remove(buffer.path)


def import_bdnb7_addresses(dpt):
    warn(
        "BDNB 7 is not used anymore. We use a more recent version of BDNB.",
        DeprecationWarning,
    )

    print(f"## Import BDNB 7 addresses in dpt {dpt}")

    src = Source("bdnb_7")
    src.set_param("dpt", dpt)

    # Create the data
    with open(src.find("adresse.csv"), "r") as f:
        print("- list addresses")
        reader = csv.DictReader(f, delimiter=",")

        data = [_convert_address_row(row) for row in reader]

    cols_str = f"({', '.join(data[0].keys())})"

    # Convert data to list of tuples for SQL insert
    data = [tuple(row.values()) for row in data]

    q = f"INSERT INTO {Address._meta.db_table} {cols_str} VALUES %s ON CONFLICT DO NOTHING"

    with connection.cursor() as cursor:
        print("- import buffer")
        try:
            # Write a sql query to copy adresses from the buffer. If there is a conflict on the primary key, do nothing
            execute_values(cursor, q, data)

            connection.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            connection.rollback()
            cursor.close()
            raise error


def _convert_address_row(row: dict) -> dict:
    return {
        "id": row["cle_interop_adr"],
        "point": row["WKT"],
        "street_number": row["numero"],
        "street_rep": row["rep"],
        "street_name": row["nom_voie"],
        "street_type": row["type_voie"],
        "city_insee_code": row["code_commune_insee"],
        "city_zipcode": row["code_postal"],
        "city_name": row["libelle_commune"],
        "source": row["source"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _get_groups_addresses_from_files(dpt):
    src = Source("bdnb_7")
    src.set_param("dpt", dpt)

    # We build a dict which associate a group_id to a list of addresses ids
    groups_to_adds = {}

    with open(src.find("rel_batiment_groupe_adresse.csv"), "r") as f:
        print("- list addresses relations")
        reader = csv.DictReader(f, delimiter=",")
        for row in reader:
            group_id = row["batiment_groupe_id"]
            add_id = row["cle_interop_adr"]

            groups_to_adds[group_id] = groups_to_adds.get(group_id, [])
            groups_to_adds[group_id].append(add_id)

    return groups_to_adds
