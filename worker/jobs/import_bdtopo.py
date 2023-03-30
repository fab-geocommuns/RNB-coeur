import csv
import os
import time

from logic.source import Source
from shapely.geometry import mapping, shape, MultiPolygon
from shapely.ops import transform
import fiona
from datetime import datetime, timezone
import psycopg2
from db import conn
from concurrent.futures import ProcessPoolExecutor, as_completed


def import_bdtopo(dpt):

    dpt = dpt.zfill(3)

    src = Source('bdtopo')
    src.set_param('dpt', dpt)



    with fiona.open(src.find(src.filename)) as f:
        total = len(f)

        print('-- read bdtopo ')

        bdgs = []

        sample_size = 50000

        start = time.perf_counter()

        executor = ProcessPoolExecutor()
        for result in executor.map(transform_bdtopo_feature, f[:sample_size], chunksize=10000):
            bdgs.append(result)



        # for feature in f:
        #
        #     bdg = transform_bdtopo_feature(feature)
        #     bdgs.append(bdg)
        #
        #     if len(bdgs) >= sample_size:
        #         break

        end = time.perf_counter()
        print(f"Elapsed time: {end - start:0.4f} seconds")


        # buffer_src = Source('buffer', {
        #     'folder': 'bdtopo',
        #     'filename': 'bdgs-{{dpt}}.csv',
        # })
        # buffer_src.set_param('dpt', dpt)
        #
        # cols = bdgs[0].keys()

        # with open(buffer_src.path, 'w') as f:
        #     print("-- writing buffer file --")
        #     writer = csv.DictWriter(f, delimiter=';', fieldnames=cols)
        #     writer.writerows(bdgs)
        #
        # with open(buffer_src.path, 'r') as f, conn.cursor() as cursor:
        #     print("-- transfer buffer to db --")
        #     try:
        #         cursor.copy_from(f, 'batid_candidate', sep=';', columns=cols)
        #         conn.commit()
        #     except (Exception, psycopg2.DatabaseError) as error:
        #         print(error)
        #         conn.rollback()
        #         cursor.close()
        #
        #
        # print('- remove buffer')
        # os.remove(buffer_src.path)



def transform_bdtopo_feature(feature) -> dict:

    shape_3d = shape(feature["geometry"])  # BD Topo provides 3D shapes
    shape_2d = transform(lambda x, y, z=None: (x, y), shape_3d)  # we convert them into 2d shapes

    multipoly = MultiPolygon([shape_2d])

    # todo : handle addresses
    address_keys = []

    bdg = {
        'shape': multipoly.wkt,
        'source': 'bdtopo',
        "source_id": feature['properties']['ID'],
        'address_keys': f"{{{','.join(address_keys)}}}",
        'created_at': datetime.now(timezone.utc)
    }

    return bdg

