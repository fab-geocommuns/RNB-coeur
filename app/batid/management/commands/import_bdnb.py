import csv
import os
from pprint import pprint

from django.core.management.base import BaseCommand
from django.db import connections
from batid.logic.building import generate_id

class Command(BaseCommand):

    import_folder = os.environ.get('IMPORT_PATH')
    csv_building_path = f"{import_folder}/bdnb-building.csv"
    csv_address_path = f"{import_folder}/bdnb-address.csv"
    csv_bdg_addr_rel_path = f"{import_folder}/bdnb-bdg-addr-rel.csv"

    bdg_addr_tmp_table = "bdg_addr_tmp"

    csv_separator = ','


    def handle(self, *args, **options):


        # self.__import_addresses()
        # self.__import_buildings()
        self.__import_bdg_addr_rels()

    def __import_bdg_addr_rels(self):

        # self.__remove_bdg_addr_rels_csv() # todo : remettre
        # self.__bdg_addr_rels_to_csv()
        self.__bdg_addr_rels_csv_to_tmp() # todo
        # self.__bdg_addr_rels_tmp_to_batid() # todo
        # self.__remove_bdg_addr_rels_csv()  # todo : remettre


    def __bdg_addr_rels_csv_to_tmp(self):

        with connections['default'].cursor() as cursor:

            # We create the tmp table
            q = f"CREATE TEMP TABLE {self.bdg_addr_tmp_table} (bdnb_id varchar(40), addr_id varchar(40))"
            cursor.execute(q)


            # We copy the csv to the tmp table
            q = f"COPY {self.bdg_addr_tmp_table} FROM %(csv_path)s WITH DELIMITER %(csv_separator)s CSV HEADER"
            cursor.execute(q, {
                'csv_path': self.csv_bdg_addr_rel_path,
                'csv_separator': self.csv_separator
            })


            # q = "SELECT b.id as building_id, " \
            #     "tmp.addr_id as addresse_id " \
            #     "FROM batid_building b " \
            #     f"JOIN {self.bdg_addr_tmp_table} tmp ON tmp.bdnb_id = b.ext_bdnb_id LIMIT 1000"
            # cursor.execute(q)
            # rows = cursor.fetchall()
            # pprint(rows)

            # Then we use the tmp table to copy relation data
            q = "INSERT INTO batid_building_addresses (building_id, address_id) " \
                "SELECT b.id as building_id, " \
                "tmp.addr_id as addresse_id " \
                "FROM batid_building b " \
                f"JOIN {self.bdg_addr_tmp_table} tmp ON tmp.bdnb_id = b.ext_bdnb_id " \
                "WHERE tmp.addr_id IS NOT NULL"
            cursor.execute(q)

            # and finally we drop the tmp table
            q = f"DROP TABLE {self.bdg_addr_tmp_table}"
            cursor.execute(q)


    def __bdg_addr_rels_to_csv(self):

        params = {
            'csv_path': self.csv_bdg_addr_rel_path,
            'csv_separator': self.csv_separator
        }

        with connections['bdnb'].cursor() as cursor:
            cursor.execute("COPY ("
                           "SELECT "
                           "batiment_construction_id as bdnb_id, "
                           "bg_a.cle_interop_adr as addr_id "
                           "FROM batiment_construction b "
                           "JOIN batiment_groupe bg ON bg.batiment_groupe_id = b.batiment_groupe_id "
                           "LEFT JOIN rel_batiment_groupe_adresse bg_a ON bg_a.batiment_groupe_id = bg.batiment_groupe_id "
                           "LEFT JOIN adresse a ON a.cle_interop_adr = bg_a.cle_interop_adr "
                           ") TO %(csv_path)s WITH DELIMITER %(csv_separator)s CSV HEADER"
                           , params)



    def __remove_bdg_addr_rels_csv(self):

        if os.path.exists(self.csv_bdg_addr_rel_path):
            os.remove(self.csv_bdg_addr_rel_path)

    def __import_addresses(self):

        # Start with a clean slate
        self.__remove_addresses_csv()

        # Build the CSV
        self.__addresses_to_csv()

        # Transfer the CSV to the BATID database
        self.__addresses_csv_to_batid()

        # Finish with a clean slate
        self.__remove_addresses_csv()

    def __remove_addresses_csv(self):

        if os.path.exists(self.csv_address_path):
            os.remove(self.csv_address_path)

    def __addresses_csv_to_batid(self):

        with connections['default'].cursor() as cursor:

            params = {
                'csv_path': self.csv_address_path,
                'csv_separator': self.csv_separator
            }

            cursor.execute("COPY batid_address "
                           "(id, street_number, street_rep, street_name, street_type, city_name, city_zipcode, source) "
                           "FROM %(csv_path)s "
                           "DELIMITER %(csv_separator)s "
                           "CSV HEADER",
                           params)

    def __addresses_to_csv(self):

        with connections['bdnb'].cursor() as cursor:
            params = {
                'csv_path': self.csv_address_path,
                'csv_separator': self.csv_separator
            }

            cursor.execute("COPY ("
                           "SELECT "
                           "cle_interop_adr as id, "
                           "numero as street_number, "
                           "rep as street_rep, "
                           "nom_voie as street_name, "
                           "type_voie as street_type, "
                           "libelle_commune as city_name, "
                           "code_postal as city_zipcode, "
                           "source "
                           "FROM adresse "
                           ") TO %(csv_path)s WITH DELIMITER %(csv_separator)s CSV HEADER",
                           params)


    def __import_buildings(self):

        # Start with a clean slate
        self.__remove_buildings_csv()

        # Build the CSV
        # todo : keep a copy of bdnb geometry in a sub table
        self.__buildings_to_csv()
        self.__gear_up_buildings_csv()

        # Transfer the CSV to the BATID database
        # todo : tester comment se comporte l'importe si on une collision de rnb_id
        self.__buildings_csv_to_batid()

        # Finish with a clean slate
        self.__remove_buildings_csv()

    def __buildings_csv_to_batid(self):

            params = {
                'csv_path': self.csv_building_path,
                'csv_separator': self.csv_separator
            }

            with connections['default'].cursor() as cursor:
                cursor.execute( "COPY batid_building "
                                "(ext_bdnb_id, point, rnb_id, source) "
                                f"FROM %(csv_path)s DELIMITER %(csv_separator)s CSV HEADER", params)

    def __remove_buildings_csv(self):

        if os.path.exists(self.csv_building_path):
            os.remove(self.csv_building_path)


    def __gear_up_buildings_csv(self):

        rows = []
        with open(self.csv_building_path, 'r') as f:

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
        with open(self.csv_building_path, 'w') as f:
            writer = csv.writer(f)
            writer.writerows(rows)


    def __buildings_to_csv(self):

        with connections['bdnb'].cursor() as cursor:

            params = {
                'csv_path': self.csv_building_path,
                'csv_separator': self.csv_separator
            }

            cursor.execute( "COPY ("
                           "SELECT batiment_construction_id as ext_bdnb_id, "
                           "ST_PointOnSurface(ST_Transform(geom_cstr, 4326)) as point "
                           # "bg_a.cle_interop_adr as ban_id, "
                           # "bg_a.lien_valide as lien_valide, "
                           # "a.source as a_source "
                           # "array_agg(bg_a.cle_interop_adr) as ext_ban_ids "
                           "FROM batiment_construction b "
                           "JOIN batiment_groupe bg ON bg.batiment_groupe_id = b.batiment_groupe_id "
                           "LEFT JOIN rel_batiment_groupe_adresse bg_a ON bg_a.batiment_groupe_id = bg.batiment_groupe_id "
                           "LEFT JOIN adresse a ON a.cle_interop_adr = bg_a.cle_interop_adr "
                           "WHERE bg_a.lien_valide OR bg_a.lien_valide IS NULL "
                           "GROUP BY b.batiment_construction_id "
                           ") TO %(csv_path)s WITH DELIMITER %(csv_separator)s CSV HEADER",
                            params)



