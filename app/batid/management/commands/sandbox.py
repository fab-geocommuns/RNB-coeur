import json
from datetime import datetime

from django.core.management.base import BaseCommand

from batid.services.source import (
    Source,
    french_cadastre_most_recent_release_date,
)


class Command(BaseCommand):
    def handle(self, *args, **options):

        today = datetime.today().date()
        cadastre_recent_release = french_cadastre_most_recent_release_date(today)

        source = Source("french_cadastre")
        source.set_param("release_date", cadastre_recent_release)
        source.set_param("dpt", "38")

        with open(source.path, "r") as f:
            data = json.load(f)
