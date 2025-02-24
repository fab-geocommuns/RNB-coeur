import json
import os
import random
import uuid
from datetime import date
from datetime import datetime
from datetime import timezone
from typing import Optional


import fiona
import psycopg2
from celery import Signature
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import WKTWriter
from django.db import connection
from django.db import transaction

from batid.models import Building
from batid.models import BuildingImport
from batid.models import Candidate
from batid.services.imports import building_import_history
from batid.services.source import BufferToCopy
from batid.services.source import Source
from batid.utils.geo import fix_nested_shells
from batid.services.administrative_areas import dpts_list


def create_bdtopo_full_import_tasks(dpt_list: list, release_date: str) -> list:

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpt_list:

        dpt_tasks = create_bdtopo_dpt_import_tasks(dpt, release_date, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    # Those inspections are commented out for now since we want to verify the created candidates first
    # inspect_tasks = create_inspection_tasks()
    # inspect_group = group(*inspect_tasks)
    # tasks.append(inspect_group)

    return tasks


def create_bdtopo_dpt_import_tasks(
    dpt: str, release_date: str, bulk_launch_id=None
) -> list:

    tasks = []

    src_params = bdtopo_src_params(dpt, release_date)

    dl_task = Signature(
        "batid.tasks.dl_source",
        args=["bdtopo", src_params],
        immutable=True,
    )
    tasks.append(dl_task)

    convert_task = Signature(
        "batid.tasks.convert_bdtopo",
        args=[src_params, bulk_launch_id],
        immutable=True,
    )
    tasks.append(convert_task)

    return tasks


def create_candidate_from_bdtopo(src_params, bulk_launch_uuid=None):

    src = Source("bdtopo")
    src.set_params(src_params)

    building_import = building_import_history.insert_building_import(
        "bdtopo", bulk_launch_uuid, src_params["dpt"]
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

            if _known_bdtopo_id(feature["properties"]["ID"]):
                continue

            candidate = _transform_bdtopo_feature(feature, srid)
            candidate = _add_import_info(candidate, building_import)
            candidate["source_version"] = src_params["date"]
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
        print(f"- remove {src.uncompress_folder} folder")
        src.remove_uncompressed_folder()


def _known_bdtopo_id(bdtopo_id: str) -> bool:

    return Building.objects.filter(
        ext_ids__contains=[{"source": "bdtopo", "id": bdtopo_id}]
    ).exists()


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


def bdtopo_src_params(dpt: str, date: str) -> dict:

    dpt = dpt.zfill(3)
    projection = _bdtopo_dpt_projection(dpt)

    return {
        "dpt": dpt,
        "projection": projection,
        "date": date,
    }


def _bdtopo_dpt_projection(dpt: str) -> str:

    default_proj = "LAMB93"

    projs = {
        "971": "RGAF09UTM20",
        "972": "RGAF09UTM20",
        "973": "UTM22RGFG95",
        "974": "RGR92UTM40S",
        "975": "RGSPM06U21",
        "976": "RGM04UTM38S",
        "977": "RGAF09UTM20",
        "978": "RGAF09UTM20",
    }

    return projs.get(dpt, default_proj)


def bdtopo_recente_release_date(before: Optional[date] = None) -> str:

    # If no date is provided, we use the current date
    if before is None:
        before = datetime.now().date()

    # First we get an ordred list of all release dates
    release_dates = sorted(
        [datetime.strptime(date, "%Y-%m-%d").date() for date in _bdtopo_release_dates()]
    )

    for idx, date in enumerate(release_dates):
        if date >= before:

            # Return the previous release date
            return release_dates[idx - 1].strftime("%Y-%m-%d")


def _bdtopo_release_dates() -> list:

    # Those are official IGN **internal** release dates.
    # They are made public 3 to 4 weeks later to the public. This delay is not fixed and can vary.

    return [
        #
        "2024-03-15",
        "2024-06-15",
        "2024-09-15",
        "2024-12-15",
        #
        "2025-03-15",
        "2025-06-15",
        "2025-09-15",
        "2025-12-15",
        #
        "2026-03-15",
        "2026-06-15",
        "2026-09-15",
        "2026-12-15",
        #
        "2027-03-15",
        "2027-06-15",
        "2027-09-15",
        "2027-12-15",
        #
        "2028-03-15",
        "2028-06-15",
        "2028-09-15",
        "2028-12-15",
        #
        "2029-03-15",
        "2029-06-15",
        "2029-09-15",
        "2029-12-15",
        #
        "2030-03-15",
        "2030-06-15",
        "2030-09-15",
        "2030-12-15",
    ]


def bdtopo_dpt_list():

    # Wallis-et-Futuna (986) and Polynésie française (987) are not available in BD Topo
    all_dpts = dpts_list()
    return [dpt for dpt in all_dpts if dpt not in ["986", "987"]]
