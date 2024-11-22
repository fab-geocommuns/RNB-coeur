from django.core.management.base import BaseCommand

from batid.models import Building
from batid.services.guess_bdg_new import Guesser


class Command(BaseCommand):
    def handle(self, *args, **kwargs):


        guesser = Guesser()
        guesser.load_work_file("./notebooks/rapprochements/AccesLibre/guesses.json")
        # guesser.report()

        guesser.matched_sample(match_reason="precise_address_match", sample_cols=["input_ext_id", "matches", "input_address"])


