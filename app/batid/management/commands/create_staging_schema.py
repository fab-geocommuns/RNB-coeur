
from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):

    def handle(self, *args, **options):

        q = "CREATE SCHEMA IF NOT EXISTS staging"

        with connections['all'].cursor() as cursor:
            cursor.execute(q)





























