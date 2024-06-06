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
        )

    def handle(self, *args, **options):
        strate = options["strate"]
        enqueue_tasks(strate)


def enqueue_tasks(strate):
    if strate == "country":
        app.send_task("batid.tasks.opendata_publish_national")
    elif strate == "department":
        for dept in dpts_list():
            app.send_task("batid.tasks.opendata_publish_department", args=[dept])
