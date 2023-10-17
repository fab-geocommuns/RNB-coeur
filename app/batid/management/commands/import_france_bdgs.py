# empty django command
from celery import chain
from django.core.management.base import BaseCommand
from batid.management.commands.import_dpt_bdgs import (
    create_tasks_list as create_tasks_list_dpt,
)


class Command(BaseCommand):
    help = "Import data for France"

    def add_arguments(self, parser):
        parser.add_argument("start_dpt", type=int, default=1)

    def handle(self, *args, **options):
        start_dpt = options["start_dpt"]
        tasks = create_tasks_list_france(start_dpt)
        chain(*tasks)()


def create_tasks_list_france(start_dpt):
    tasks = []
    for dpt in range(start_dpt, 97):
        dpt = str(dpt).zfill(2)
        tasks.append(create_tasks_list_dpt(dpt, "all"))
    # flattern the list
    tasks = [item for sublist in tasks for item in sublist]
    return tasks
