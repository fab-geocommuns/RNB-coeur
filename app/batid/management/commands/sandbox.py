import os
from pprint import pprint

from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):


    def handle(self, *args, **options):

        # Building.objects.all().delete()

        buffer_folder = os.environ.get('BUFFER_PATH')

        path = f"{buffer_folder}/test.csv"

        with open(path, 'w') as creating_new_csv_file:
            pass











