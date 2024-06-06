# empty django command
from celery import chain
from celery import Signature
from django.core.management.base import BaseCommand

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

        tasks = create_tasks_list(strate)
        chain(*tasks)()


def create_tasks_list(strate, bulk_launch_uuid=None):
    tasks = []

    if strate == "country":
        tasks.append(Signature("batid.tasks.opendata_publish_national", immutable=True))
    elif strate == "department":
        for dept in dpts_list():
            tasks.append(
                Signature(
                    "batid.tasks.opendata_publish_department",
                    args=[dept],
                    immutable=True,
                )
            )
            print(f"code_dept: {dept}")
    return tasks
