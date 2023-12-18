import csv
import json
from pprint import pprint

import fiona
from django.contrib.gis.geos import GEOSGeometry, WKTWriter
from django.core.management.base import BaseCommand
from shapely.ops import transform
from shapely.geometry import shape

from batid.models import Building, Candidate
from batid.services.candidate import Inspector
from batid.services.source import Source
from batid.services.imports.import_bdtopo import import_bdtopo
from batid.tasks import dl_source


class Command(BaseCommand):
    def handle(self, *args, **options):
        src = Source("bdtopo_2023_09_972")

        with fiona.open(src.find(src.filename)) as file:
            srid = int(file.crs["init"].split(":")[1])

            errors = []
            features_c = 0

            for feature in file:
                features_c += 1
                print(features_c)

                # if c >= 5000:
                #     break

                # if feature["properties"]["ID"] != "BATIMENT0000002334063641":
                #     continue

                # geom = no_transform(feature, srid)
                # print("no transform")
                # print(geom.valid)
                # print(geom.valid_reason)

                new_geom = new_convert(feature, srid)
                # print("new geom")
                # print(new_geom.valid)
                # print(new_geom.valid_reason)
                # print(new_geom.json)

                if not new_geom.valid:
                    errors.append(new_geom.json)

                # if errors_c == 3:
                #     break

                # old_geom = old_convert(feature, srid)
                # print("old geom")
                # print(old_geom.valid)
                # print(old_geom.valid_reason)

                # break

            for e in errors:
                print("---")
                print(e)

            print(f"errors : {len(errors)}")
            print(f"features : {features_c}")


def no_transform(feature, from_srid):
    geom = GEOSGeometry(json.dumps(dict(feature["geometry"])))
    geom.srid = from_srid

    geom.transform(4326)

    return geom


def old_convert(feature, from_srid):
    shape_3d = shape(feature["geometry"])  # BD Topo provides 3D shapes
    shape_2d = transform(
        lambda x, y, z=None: (x, y), shape_3d
    )  # we convert them into 2d shapes

    geom = GEOSGeometry(shape_2d.wkt)
    geom.srid = from_srid

    geom.transform(4326)

    if not geom.valid:
        geom = geom.buffer(0)

    return geom


def new_convert(feature, from_srid):
    geom = GEOSGeometry(json.dumps(dict(feature["geometry"])))
    geom.srid = from_srid

    geom.transform(4326)

    writer = WKTWriter()
    writer.outdim = 2

    wkt = writer.write(geom)

    geom = GEOSGeometry(wkt)

    if not geom.valid:
        geom = geom.buffer(0)

    return geom


def is_clockwise(polygon):
    """
    Determine if the points in a polygon are arranged in a clockwise order.
    Args:
    polygon (list): A list of tuples/lists representing the points of the polygon.

    Returns:
    bool: True if the points are in a clockwise order, False otherwise.
    """
    total = 0
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        total += (x2 - x1) * (y2 + y1)
    return total > 0
