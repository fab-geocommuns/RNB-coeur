import json
from pprint import pprint

import geopandas as gpd
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.core.serializers import serialize
from shapely.geometry import mapping

from batid.models import Building
from batid.services.guess_bdg_new import (
    Guesser,
    PartialRoofHandler,
    GuessSqlitePersister,
)


class Command(BaseCommand):
    def handle(self, *args, **options):
        # inputs = []
        #
        #
        #  # Persists the inputs
        #  guesser = Guesser()
        #  guesser.persister = GuessSqlitePersister('lyon_complete')
        #  guesser.load_inputs(inputs)
        #  guesser.save()
        #
        # # Resume guess work
        #  guesser = Guesser()
        #  guesser.persister = GuessSqlitePersister('lyon_complete')
        #  guesser.handlers = [PartialRoofHandler()]
        #  guesser.guess_all()

        inputs = [
            {
                "ext_id": "aaa",
                "address": "1 rue de la paix, 75002 Paris",
            },
            {
                "ext_id": "bbb",
                "address": "2 rue de la paix, 75002 Paris",
            },
        ]

        # guesser = Guesser()
        # guesser.load_inputs(inputs)
        #
        # guesser.persister = GuessSqlitePersister("lyon_complete")
        # guesser.save()

        guesser = Guesser()
        guesser.persister = GuessSqlitePersister("lyon_complete")
        guesser.handlers = [PartialRoofHandler()]
        guesser.guess_all()
