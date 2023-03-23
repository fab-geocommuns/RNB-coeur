import csv

from django.core.management.base import BaseCommand
from django.db import connections
from batid.logic.source import Source
from datetime import datetime, timezone

class Command(BaseCommand):



    def add_arguments(self, parser):
        parser.add_argument('dpt', type=str)

    def handle(self, *args, **options):

        src = Source('bdnb_7')

        groups_addresses = {}

        with open(src.find('rel_batiment_groupe_adresse.csv'), 'r') as f:
            reader = csv.DictReader(f, delimiter=',')
            for row in reader:

                group_id = row['batiment_groupe_id']

                if group_id not in groups_addresses:
                    groups_addresses[group_id] = []
                groups_addresses[group_id].append(row['cle_interop_adr'])

        bdgs = []

        with open(src.find('batiment_construction.csv'), 'r') as f:
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

        cols = bdgs[0].keys()

        with open(buffer_src.path, 'w') as f:
            writer = csv.DictWriter(f, delimiter=';', fieldnames=cols)
            writer.writerows(bdgs)

        with open(buffer_src.path, 'r') as f, connections['default'].cursor() as cursor:

            cursor.copy_from(f, 'batid_candidate', sep=';', columns=cols)