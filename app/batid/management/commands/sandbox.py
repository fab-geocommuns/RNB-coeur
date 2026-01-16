import cProfile
import io
import pstats

from django.core.management.base import BaseCommand

from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        pr = cProfile.Profile()
        pr.enable()
        create_candidate_from_bdtopo(
            {"dpt": "035", "projection": "LAMB93", "date": "2025-12-15"}
        )
        pr.disable()

        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumtime")
        ps.print_stats(50)
        print(s.getvalue())
