# empty django command
from django.core.management.base import BaseCommand

from app.celery import app
from batid.services.administrative_areas import dpts_list


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
            "--start-dpt",
            type=str,
            help="Only for strate=department, allow to start at a specific department code.",
        )

    def handle(self, *args, **options):
        strate = options["strate"]
        starting_code = options.get("start_dpt", None)
        enqueue_tasks(strate, starting_code)


def enqueue_tasks(strate, starting_code=None):
    if strate == "country":
        app.send_task("batid.tasks.opendata_publish_national")
    elif strate == "department":
        dpts = dpts_list()

        if starting_code is not None:
            dpts = dpts[dpts.index(starting_code) :]

        for dept in dpts:
            app.send_task("batid.tasks.opendata_publish_department", args=[dept])
