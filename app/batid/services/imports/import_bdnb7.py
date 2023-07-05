import csv
import json
import os

import psycopg2
from django.db import connection
from batid.services.source import Source, BufferToCopy
from datetime import datetime, timezone


def import_bdnb7(dpt):
    src = Source("bdnb_7")
    src.set_param("dpt", dpt)

    print(f"## Import BDNB 7 in dpt {dpt}")

    groups_addresses = _get_groups_addresses_from_files(dpt)

    bdgs = []

    with open(src.find("batiment_construction.csv"), "r") as f:
        print("- list buildings")
        reader = csv.DictReader(f, delimiter=",")
        for row in list(reader):
            group_id = row["batiment_groupe_id"]

            addresses = []
            if group_id in groups_addresses:
                addresses = groups_addresses[group_id]

            bdg = {
                "shape": row["WKT"],
                "source": "bdnb_7",
                "is_light": False,
                "source_id": row["batiment_construction_id"],
                "addresses": json.dumps(addresses),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            bdgs.append(bdg)

    buffer = BufferToCopy()
    print(f"- write buffer to {buffer.path}")
    buffer.write_data(bdgs)

    cols = bdgs[0].keys()

    with open(buffer.path, "r") as f:
        with connection.cursor() as cursor:
            print("- import buffer")
            try:
                cursor.copy_from(f, "batid_candidate", sep=";", columns=cols)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cursor.close()
                raise error

    print("- remove buffer")
    os.remove(buffer.path)


def _convert_address_row(row: dict) -> dict:
    return {
        "id": row["cle_interop_adr"],
        "street_number": row["numero"],
        "street_rep": row["rep"],
        "street_name": row["nom_voie"],
        "street_type": row["type_voie"],
        "insee_code": row["code_commune_insee"],
        "zip_code": row["code_postal"],
        "city_name": row["libelle_commune"],
        "source": row["source"],
    }


def _get_groups_addresses_from_files(dpt):
    src = Source("bdnb_7")
    src.set_param("dpt", dpt)

    # First we build a dict with address_id as key and a list of group_id as value
    # We use the file containing the relation between addresses and groups
    add_to_groups = {}

    with open(src.find("rel_batiment_groupe_adresse.csv"), "r") as f:
        print("- list addresses")
        reader = csv.DictReader(f, delimiter=",")
        for row in reader:
            group_id = row["batiment_groupe_id"]
            add_id = row["cle_interop_adr"]

            if add_id not in add_to_groups:
                add_to_groups[add_id] = []
            add_to_groups[add_id].append(group_id)

    # Then, using the addresses file, we build the final dict
    # The dict has group_id as key and a list of addresses as value
    # The list of adresses of each group contains all the details of the adresse
    groups_to_adds = {}

    with open(src.find("adresse.csv"), "r") as f:
        reader = csv.DictReader(f, delimiter=",")

        for row in reader:
            add_id = row["cle_interop_adr"]
            if add_id not in add_to_groups:
                continue

            for group_id in add_to_groups[add_id]:
                if group_id not in groups_to_adds:
                    groups_to_adds[group_id] = []
                groups_to_adds[group_id].append(_convert_address_row(row))

    return groups_to_adds
