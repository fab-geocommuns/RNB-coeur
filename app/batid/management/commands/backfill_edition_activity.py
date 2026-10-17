from datetime import date, datetime, timedelta, timezone

from batid.services.edition_activity import record_edition_activity
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Backfill the EditionActivity table from the building history, one day at a time"

    def add_arguments(self, parser):
        parser.add_argument("--since", type=str, default="2023-01-01")
        parser.add_argument(
            "--until",
            type=str,
            default=(date.today() + timedelta(days=1)).isoformat(),
            help="Exclusive end date (default: tomorrow)",
        )

    def handle(self, *args, **options):
        since = date.fromisoformat(options["since"])
        until = date.fromisoformat(options["until"])

        print(f"Backfilling edition activity from {since} to {until} (exclusive)")

        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = 0;")

        total = 0
        d = since
        while d < until:
            day_start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            inserted = record_edition_activity(day_start, day_start + timedelta(days=1))
            total += inserted
            if inserted:
                print(f"{d} | {inserted} editions")
            d += timedelta(days=1)

        print(f"Done: {total} editions recorded")
