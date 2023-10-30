from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import connection

from batid.list_bdg import public_bdg_queryset
from batid.services.guess_bdg import BuildingGuess
from batid.tasks import fill_shapewhs84_col


class Command(BaseCommand):
    def handle(self, *args, **options):
        fill_shapewhs84_col()
