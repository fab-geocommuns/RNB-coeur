# empty django command
from celery import chain
from django.core.management.base import BaseCommand
from batid.management.commands.import_dpt_bdgs import create_tasks_list


class Command(BaseCommand):
    help = "Import data for France"

    def handle(self, *args, **options):
        tasks = []
        for dpt in range(1, 96):
            dpt = str(dpt).zfill(2)
            tasks.append(create_tasks_list(dpt, "all"))
        # flattern the list
        tasks = [item for sublist in tasks for item in sublist]
        chain(*tasks)()
