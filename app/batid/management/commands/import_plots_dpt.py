from datetime import datetime
from django.core.management.base import BaseCommand
from celery import chain, Signature


class Command(BaseCommand):
    help = "Import plots (cadastre) for a given departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt):
    tasks = []
    tasks.append(Signature("batid.tasks.dl_source", args=["plot", dpt], immutable=True))
    tasks.append(Signature("batid.tasks.import_plots", args=[dpt], immutable=True))
    return tasks