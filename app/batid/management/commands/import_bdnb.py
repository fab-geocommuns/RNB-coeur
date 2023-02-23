import csv
import os
from pprint import pprint

from django.core.management.base import BaseCommand
from django.db import connections
from batid.logic.building import generate_id

class Command(BaseCommand):

    import_folder = os.environ.get('IMPORT_PATH')
    csv_path = f"{import_folder}/bdnb.csv"

    csv_separator = ','


    def handle(self, *args, **options):

        # Start with a clean slate
        self.__remove_csv()

        # Build the CSV
        # todo : keep a copy of bdnb geometry in a sub table
        self.__bdnb_to_csv()
        self.__gear_up_csv()

        # Transfer the CSV to the BATID database
        # todo : tester comment se comporte l'importe si on une collision de rnb_id
        self.__csv_to_batid()

        # Finish with a clean slate
        self.__remove_csv()

    def __csv_to_batid(self):

            with connections['default'].cursor() as cursor:
                cursor.execute( "COPY batid_building "
                                "(ext_bdnb_id, point, ext_ban_ids, rnb_id, source) "
                                f"FROM '{self.csv_path}' DELIMITER '{self.csv_separator}' CSV HEADER")

    def __remove_csv(self):

        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)


    def __gear_up_csv(self):

        rows = []
        with open(self.csv_path, 'r') as f:

            # Get all rows in memory
            reader = csv.reader(f)

            header = next(reader)
            header.append('rnb_id')
            header.append('source')
            rows.append(header)

            for idx, row in enumerate(list(reader)):
                row.append(generate_id())
                row.append("rnb")
                rows.append(row)

        # Write the new CSV
        with open(self.csv_path, 'w') as f:
            writer = csv.writer(f)
            writer.writerows(rows)


    def __bdnb_to_csv(self):

        with connections['bdnb'].cursor() as cursor:

            cursor.execute( "COPY ("
                           "SELECT batiment_construction_id as ext_bdnb_id, "
                           "ST_PointOnSurface(ST_Transform(geom_cstr, 4326)) as point, "
                           # "bg_a.cle_interop_adr as ban_id, "
                           # "bg_a.lien_valide as lien_valide, "
                           # "a.source as a_source "
                           "array_agg(bg_a.cle_interop_adr) as ext_ban_ids "
                           "FROM batiment_construction b "
                           "JOIN batiment_groupe bg ON bg.batiment_groupe_id = b.batiment_groupe_id "
                           "LEFT JOIN rel_batiment_groupe_adresse bg_a ON bg_a.batiment_groupe_id = bg.batiment_groupe_id "
                           "LEFT JOIN adresse a ON a.cle_interop_adr = bg_a.cle_interop_adr "
                           # "WHERE batiment_construction_id = 'BATIMENT0000000301140164-1' "
                           "WHERE bg_a.lien_valide OR bg_a.lien_valide IS NULL "
                           "GROUP BY b.batiment_construction_id "
                           f") TO '{self.csv_path}' WITH DELIMITER '{self.csv_separator}' CSV HEADER"
                           )



