import csv
import json
import os

from django.contrib.gis.geos import GEOSGeometry, WKTWriter
from fiona.crs import CRS

from batid.models import Candidate, BuildingImport
from batid.services.imports import building_import_history

from batid.services.source import Source, bdtopo_source_switcher
from shapely.geometry import shape, MultiPolygon
from shapely.ops import transform
import fiona
from datetime import datetime, timezone
import psycopg2
from django.db import connection, transaction
import random


def import_bdtopo(bdtopo_edition, dpt, bulk_launch_uuid=None):
    dpt = dpt.zfill(3)

    source_name = bdtopo_source_switcher(bdtopo_edition, dpt)

    building_import = building_import_history.insert_building_import(
        source_name, bulk_launch_uuid, dpt
    )

    src = Source(source_name)
    src.set_param("dpt", dpt)

    with fiona.open(src.find(src.filename)) as f:
        print("-- read bdtopo ")

        # We extract the SRID from the crs attribute of the shapefile
        srid = int(f.crs["init"].split(":")[1])

        candidates = []

        c = 0
        for feature in f:
            c += 1
            print(f"--- {c} ---")
            candidate = _transform_bdtopo_feature(feature, srid)
            candidate = _add_import_info(candidate, building_import)
            candidates.append(candidate)

        buffer_src = Source(
            "buffer",
            {
                "folder": "bdtopo",
                "filename": "bdgs-{{dpt}}.csv",
            },
        )
        buffer_src.set_param("dpt", dpt)

        cols = candidates[0].keys()

        with open(buffer_src.path, "w") as f:
            print("-- writing buffer file --")
            writer = csv.DictWriter(f, delimiter=";", fieldnames=cols)
            writer.writerows(candidates)

        with open(buffer_src.path, "r") as f:
            with transaction.atomic():
                print("-- transfer buffer to db --")
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
        os.remove(buffer_src.path)


def _transform_bdtopo_feature(feature, from_srid) -> dict:
    geom_wkt = feature_to_wkt(feature, from_srid)

    address_keys = []

    candidate_dict = {
        "shape": geom_wkt,
        "is_light": True if feature["properties"]["LEGER"] == "Oui" else False,
        "source": "bdtopo",
        "source_version": "2022-12-15",
        "source_id": feature["properties"]["ID"],
        "address_keys": f"{{{','.join(address_keys)}}}",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        # TODO: extract the function
        "random": random.randint(0, 1000000000),
    }

    return candidate_dict


def _add_import_info(candidate, building_import: BuildingImport):
    candidate["created_by"] = json.dumps({"source": "import", "id": building_import.id})
    return candidate


def feature_to_wkt(feature, from_srid):
    geom = GEOSGeometry(json.dumps(dict(feature["geometry"])))
    geom.srid = from_srid

    geom.transform(4326)

    writer = WKTWriter()
    writer.outdim = 2

    return writer.write(geom)
