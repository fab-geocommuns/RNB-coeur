# empty django command
from django.core.management.base import BaseCommand

from app.celery import app
from batid.management.commands.utils.administrative_areas import dpts_list


class Command(BaseCommand):
    help = "Publish opendata for each department or full France"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strate",
            type=str,
            default="department",
            choices=["country", "department"],
        ), 
        parser.add_argument(
            "--start-at",
            type=str,
            help="Only for strate=department, allow to start at a specific department code.",
        )

    def handle(self, *args, **options):
        strate = options["strate"]
        if options["start-at"]:
            starting_code = options["start-at"]
        else:
            starting_code = None
        enqueue_tasks(strate, starting_code)


def enqueue_tasks(strate, starting_code=None):
    if strate == "country":
        app.send_task("batid.tasks.opendata_publish_national")
    elif strate == "department":
        process = False
        for dept in dpts_list():
            if dept == starting_code:
                process = True
            if starting_code is None or process is True:
                app.send_task("batid.tasks.opendata_publish_department", args=[dept])
