# empty django command
from django.core.management.base import BaseCommand

from batid.management.commands.utils.administrative_areas import dpts_list
from batid.services.data_gouv_publication import publish


class Command(BaseCommand):
    help = "Publish opendata for each department or full France"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strate", type=str, default="department",
            choices=['country', 'department']
        )

    def handle(self, *args, **options):
        strate = options["strate"]

        if strate == "country":
            areas_list = ["nat"]
        elif strate == "department":
            areas_list = dpts_list()
        tasks = publish(areas_list)
