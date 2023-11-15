from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from batid.list_bdg import list_bdgs
from batid.services.building import add_default_status
from batid.services.guess_bdg import BuildingGuess


class Command(BaseCommand):
    def handle(self, *args, **options):
        add_default_status()
