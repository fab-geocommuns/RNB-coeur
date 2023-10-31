from django.core.management.base import BaseCommand
from celery import chain, Signature


class Command(BaseCommand):
    help = "Import BDNB for a given departement (create candidates)"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt):
    bdnb_dpt = dpt.lower()
    tasks = []
    tasks.append(
        Signature("batid.tasks.dl_source", args=["bdnb_7", bdnb_dpt], immutable=True)
    )
    tasks.append(
        Signature(
            "batid.tasks.import_bdnb7_addresses",
            args=[bdnb_dpt],
            immutable=True,
        )
    )
    tasks.append(
        Signature("batid.tasks.import_bdnb7_bdgs", args=[bdnb_dpt], immutable=True)
    )
    return tasks
