from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from batid.list_bdg import list_bdgs
from batid.services.guess_bdg import BuildingGuess


class Command(BaseCommand):
    def handle(self, *args, **options):
        qs = list_bdgs(
            {
                "insee_code": "33063",
            }
        )

        print(qs.query)
