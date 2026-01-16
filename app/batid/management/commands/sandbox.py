import time
import cProfile, pstats, io
from django.core.management.base import BaseCommand
from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo

from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id


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
