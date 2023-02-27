from pprint import pprint

from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):


    def handle(self, *args, **options):

        # Building.objects.all().delete()

        with connections['bdnb'].cursor() as cursor:

            params = {
                'csv_path': self.csv_address_path,
                'csv_separator': self.csv_separator
            }

            cursor.execute( "COPY ("
                            "SELECT numero as street_number, "
                            "rep as street_rep, "
                            "nom_voie as street_name, "
                            "type_voie as street_type, "
                            "libelle_commune as city_name, "
                            "code_postal as city_zipcode, "
                            "source "
                            "FROM adresse "
                            ") TO %(csv_path)s WITH DELIMITER %(csv_separator)s CSV HEADER",
                            params)











