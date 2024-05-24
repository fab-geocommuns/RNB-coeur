from celery import chain
from celery import Signature
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import cities for a given departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt):
    tasks = []
    tasks.append(Signature("batid.tasks.import_cities", args=[dpt], immutable=True))
    return tasks
