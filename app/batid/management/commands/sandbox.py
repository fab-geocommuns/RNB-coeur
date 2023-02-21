from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):


    def handle(self, *args, **options):

        with connections['bdnb'].cursor() as cursor:

            cursor.execute("SELECT * FROM batiment_construction LIMIT 10")
            rows = cursor.fetchall()
            print(rows)