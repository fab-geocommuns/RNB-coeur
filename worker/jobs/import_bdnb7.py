import csv
import os

import psycopg2
from db import conn
from logic.source import Source
from datetime import datetime, timezone

def import_bdnb7(dpt):

    src = Source('bdnb_7')
    src.set_param('dpt', dpt)

    groups_addresses = {}

    with open(src.find('rel_batiment_groupe_adresse.csv'), 'r') as f:
        print('- list addresses')
        reader = csv.DictReader(f, delimiter=',')
        for row in reader:

            group_id = row['batiment_groupe_id']

            if group_id not in groups_addresses:
                groups_addresses[group_id] = []
            groups_addresses[group_id].append(row['cle_interop_adr'])

    bdgs = []

    with open(src.find('batiment_construction.csv'), 'r') as f:
        print('- list buildings')
        reader = csv.DictReader(f, delimiter=',')
        for row in list(reader):
            group_id = row['batiment_groupe_id']
            address_keys = groups_addresses.get(group_id, [])

            bdg = {
                'shape': row['WKT'],
                'source': 'bdnb_7',
                "source_id": row['batiment_construction_id'],
                'address_keys': f"{{{','.join(address_keys)}}}",
                'created_at': datetime.now(timezone.utc)
            }
            bdgs.append(bdg)

    buffer_src = Source('buffer', {
        'folder': 'bdnb_7',
        'filename': 'bdgs-buffer-{{dpt}}.csv',
    })
    buffer_src.set_param('dpt', dpt)

    cols = bdgs[0].keys()

    with open(buffer_src.path, 'w') as f:
        print('- write buffer')
        writer = csv.DictWriter(f, delimiter=';', fieldnames=cols)
        writer.writerows(bdgs)

    with open(buffer_src.path, 'r') as f, conn.cursor() as cursor:
        print('- import buffer')
        try:
            cursor.copy_from(f, 'batid_candidate', sep=';', columns=cols)
            conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            conn.rollback()
            cursor.close()

    #print('- remove buffer')
    #os.remove(buffer_src.path)