# empty django command
import csv
import json
from datetime import datetime, timezone
from pprint import pprint

from django.core.management import BaseCommand
from django.contrib.gis.geos import GEOSGeometry, Polygon, MultiPolygon, Point
from batid.logic.source import Source
import fiona
from django.db import connections
from fiona import Feature, Geometry
from shapely.geometry import mapping, shape
from shapely.ops import transform
from django.conf import settings


class Command(BaseCommand):

    def handle(self, *args, **options):

        source = Source('bdtopo')


        with fiona.open(source.path) as f:

            bdgs = []
            c = 0
            for feature in f:

                c += 1
                print(c)

                # Into shapely object
                shape_3d = shape(feature['geometry']) # BD Topo provides 3D shapes
                shape_2d = transform(lambda x, y, z=None: (x, y), shape_3d) # we convert them into 2d shapes

                geom_p = GEOSGeometry(shape_2d.wkt)
                geom_mp = MultiPolygon([geom_p])
                geom_mp.srid = 2154 # BD Topo is in Lambert 93

                address_keys = []

                bdg = {
                    'shape': geom_mp.wkt,
                    'source': 'bdtopo',
                    "source_id": feature['properties']['ID'],
                    'address_keys': f"{{{','.join(address_keys)}}}",
                    'created_at': datetime.now(timezone.utc)
                }
                bdgs.append(bdg)

            buffer_source = Source('bdtopo_buffer')
            cols = bdgs[0].keys()

            with open(buffer_source.path, 'w') as f:
                print("-- writing buffer file --")
                writer = csv.DictWriter(f, delimiter=';', fieldnames=cols)
                writer.writerows(bdgs)

            with open(buffer_source.path, 'r') as f, connections['default'].cursor() as cursor:
                print("-- transfer buffer to db --")
                cursor.copy_from(f, 'batid_candidate', sep=';', columns=cols)













