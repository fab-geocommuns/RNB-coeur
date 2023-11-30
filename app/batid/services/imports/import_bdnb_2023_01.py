import csv
import json
import os
from pprint import pprint

import psycopg2
from django.contrib.gis.geos import GEOSGeometry
from datetime import datetime, timezone

from django.db import transaction, connection
from psycopg2.extras import execute_values

from batid.models import Candidate, Address
from batid.services.imports import building_import_history
from batid.services.source import Source, BufferToCopy


def import_bdnd_2023_01_bdgs(dpt):
    print("## Import BDNB 2023_01 buildings")

    source_id = "bdnb_2023_01"

    building_import = building_import_history.insert_building_import(
        source_id, None, dpt
    )

    src = Source(source_id)
    src.set_param("dpt", dpt)
    file_path = src.find(f"{dpt}_bdgs.csv")

    with open(file_path, "r") as f:
        print("- list buildings")
        reader = csv.DictReader(f)

        candidates = []
        for row in list(reader):
            geom = GEOSGeometry(row["geom_batiment_construction"])
            geom.srid = 4326
            if row["reelle_geom_batiment_construction"] != "t":
                geom = geom.point_on_surface

            # replace addresses keys with only one item = null
            add_keys = row["cle_interop_adr"]
            if add_keys == "{NULL}":
                add_keys = "{}"

            candidate = {
                "shape": geom.wkt,
                "source": "bdnb",
                "source_version": "2023_01",
                "is_light": False,
                "source_id": row["batiment_construction_id"],
                "address_keys": add_keys,
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


def import_bdnd_2023_01_addresses(dpt):
    print("## Import BDNB 2023_01 addresses")

    src = Source("bdnb_2023_01")
    src.set_param("dpt", dpt)
    file_path = src.find(f"{dpt}_adresses.csv")

    with open(file_path, "r") as f:
        reader = csv.DictReader(f, delimiter=",")

        addresses = []

        for row in reader:
            point = GEOSGeometry(row["geom"])
            point.srid = 4326

            address = {
                "id": row["cle_interop_adr"],
                "source": "bdnb",
                "point": point.wkt,
                "street_number": row["numero"],
                "street_rep": row["rep"],
                "street_name": row["nom_voie"],
                "street_type": row["type_voie"],
                "city_name": row["commune"],
                "city_zipcode": row["code_postal"],
                "city_insee_code": row["code_commune_insee"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            addresses.append(address)

        cols_str = f"({', '.join(addresses[0].keys())})"

        data = [tuple(row.values()) for row in addresses]

        q = f"INSERT INTO {Address._meta.db_table} {cols_str} VALUES %s ON CONFLICT DO NOTHING"

        with connection.cursor() as cursor:
            print("- import buffer")
            try:
                execute_values(cursor, q, data)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cursor.close()
                raise error
