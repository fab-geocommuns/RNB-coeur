import csv
import os
from app.batid.services.imports import building_import_history

from batid.services.source import Source
from shapely.geometry import shape, MultiPolygon
from shapely.ops import transform
import fiona
from datetime import datetime, timezone
import psycopg2
from django.db import connection, transaction


def import_bdtopo(dpt, bulk_launch_uuid=None):
    dpt = dpt.zfill(3)

    building_import = building_import_history.insert_building_import(
        "bdtopo", bulk_launch_uuid, dpt
    )

    src = Source("bdtopo")
    src.set_param("dpt", dpt)

    with fiona.open(src.find(src.filename)) as f:
        print("-- read bdtopo ")

        bdgs = []

        for feature in f:
            bdg = _transform_bdtopo_feature(feature)
            bdgs.append(bdg)

        buffer_src = Source(
            "buffer",
            {
                "folder": "bdtopo",
                "filename": "bdgs-{{dpt}}.csv",
            },
        )
        buffer_src.set_param("dpt", dpt)

        cols = bdgs[0].keys()

        with open(buffer_src.path, "w") as f:
            print("-- writing buffer file --")
            writer = csv.DictWriter(f, delimiter=";", fieldnames=cols)
            writer.writerows(bdgs)

        with open(buffer_src.path, "r") as f:
            with transaction.atomic():
                print("-- transfer buffer to db --")
                try:
                    with connection.cursor() as cursor:
                        cursor.copy_from(f, "batid_candidate", sep=";", columns=cols)

                    building_import_history.increment_created_candidates(
                        building_import, len(bdgs)
                    )

                except (Exception, psycopg2.DatabaseError) as error:
                    raise error

        print("- remove buffer")
        os.remove(buffer_src.path)


def _transform_bdtopo_feature(feature) -> dict:
    multipoly = feature_to_multipoly(feature)

    # todo : handle addresses
    address_keys = []

    bdg = {
        "shape": multipoly.wkt,
        "is_light": True if feature["properties"]["LEGER"] == "Oui" else False,
        "source": "bdtopo",
        "source_id": feature["properties"]["ID"],
        "address_keys": f"{{{','.join(address_keys)}}}",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    return bdg


def feature_to_multipoly(feature) -> MultiPolygon:
    shape_3d = shape(feature["geometry"])  # BD Topo provides 3D shapes
    shape_2d = transform(
        lambda x, y, z=None: (x, y), shape_3d
    )  # we convert them into 2d shapes

    return MultiPolygon([shape_2d])
