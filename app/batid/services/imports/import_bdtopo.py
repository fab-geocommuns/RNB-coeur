import json
import os
import random
from datetime import datetime
from datetime import timezone

import fiona
import psycopg2
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import WKTWriter
from django.db import connection
from django.db import transaction

from batid.models import BuildingImport
from batid.models import Candidate
from batid.services.imports import building_import_history
from batid.services.source import bdtopo_source_switcher
from batid.services.source import BufferToCopy
from batid.services.source import Source
from batid.utils.geo import fix_nested_shells


def import_bdtopo(src_params, bulk_launch_uuid=None):

    src = Source("bdtopo")
    src.set_params(src_params)

    building_import = building_import_history.insert_building_import(
        "bdtopo", bulk_launch_uuid, dpt
    )

    with fiona.open(src.find(src.filename)) as f:
        print("-- read bdtopo ")

        # We extract the SRID from the crs attribute of the shapefile
        srid = int(f.crs["init"].split(":")[1])

        candidates = []

        for feature in f:
            # We skip the light buildings
            if feature["properties"]["LEGER"] == "Oui":
                continue

            candidate = _transform_bdtopo_feature(feature, srid)
            candidate = _add_import_info(candidate, building_import)
            candidate["source_version"] = bdtopo_edition
            candidates.append(candidate)

        buffer = BufferToCopy()
        buffer.write_data(candidates)

        cols = candidates[0].keys()

        with open(buffer.path, "r") as f:
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
        os.remove(buffer.path)


def _transform_bdtopo_feature(feature, from_srid) -> dict:
    geom_wkt = feature_to_wkt(feature, from_srid)

    address_keys = []

    candidate_dict = {
        "shape": geom_wkt,
        "is_light": feature["properties"]["LEGER"] == "Oui",
        "source": "bdtopo",
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
    # From shapefile feature to GEOS geometry
    geom = GEOSGeometry(json.dumps(dict(feature["geometry"])))
    geom.srid = from_srid

    # From local SRID to WGS84
    geom.transform(4326)

    # From 3D geom to 2D geom wkt
    writer = WKTWriter()
    writer.outdim = 2
    wkt = writer.write(geom)

    # Back to geom
    geom = GEOSGeometry(wkt)

    # Eventually, fix nested shells
    if not geom.valid and "Nested shells" in geom.valid_reason:
        geom = fix_nested_shells(geom)

    return geom.wkt
