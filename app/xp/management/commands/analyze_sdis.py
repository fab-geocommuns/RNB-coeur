from django.core.management.base import BaseCommand

from batid.services.source import Source
import pandas as pd


class Command(BaseCommand):
    FILENAME = "erp_geolocalises_20112020.json"

    def handle(self, *args, **options):
        raw_src = Source("xp-sdis", {"folder": "xp-sdis", "filename": self.FILENAME})

        # open json with pandas

        df = pd.read_json(raw_src.path)

        # First count rows
        print(f"Number of rows: {len(df)}")

        # Then count rows with guess_done = True
        print(
            f"Number of rows with guess_done = True: {len(df[df['guess_done'] == True])}"
        )
