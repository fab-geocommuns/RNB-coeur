import csv
from io import StringIO

from django.core.management.base import BaseCommand

from batid.services.contributions import export_format


class Command(BaseCommand):
    def handle(self, *args, **options):

        pass
