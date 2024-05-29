from django.core.management.base import BaseCommand

from batid.services.geocoders import BanBatchGeocoder
from batid.services.guess_bdg_new import Guesser


class Command(BaseCommand):
    def handle(self, *args, **options):

        g = BanBatchGeocoder()
        r = g.geocode_in_memory([])

    def note(self):
        f_path = "notebooks/rapprochements/histologe/guess.json"

        guesser = Guesser()
        guesser.load_work_file(f_path)

        guesser.report()

        guesser.display_matches(
            "precise_address_match", 20, ["input_address", "match_rnb_id"]
        )
