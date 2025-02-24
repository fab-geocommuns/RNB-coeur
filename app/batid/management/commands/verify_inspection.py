from datetime import datetime

from django.core.management.base import BaseCommand

from batid.services.candidate import display_report


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("since", type=str, default=None)
        parser.add_argument("--checks", type=str, default="all")

    def handle(self, *args, **options):

        since = options["since"]
        # "Since" is mandatory
        if not since:
            print("Please provide a date.")
            return
        # "Since" must be a valid date
        try:
            since = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            print("Please provide a valid date.")
            return

        display_report(since, options["checks"])
