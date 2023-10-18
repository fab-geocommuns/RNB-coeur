from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from batid.list_bdg import public_bdg_queryset
from batid.services.guess_bdg import BuildingGuess


class Command(BaseCommand):
    def handle(self, *args, **options):
        point = Point(5.726110585668517, 45.181819080459725, srid=4326)

        guess = BuildingGuess()
        guess.set_params(point=point)

        qs = guess.get_queryset()

        print(len(qs), " batiments trouvés")

        for b in qs:
            print("--")
            print(b.rnb_id, " rnb_id")
            print(b.score, " score")
