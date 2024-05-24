from celery import chain
from celery import Signature
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import BDNB for a given departement (create candidates)"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt, bulk_launch_uuid=None):
    tasks = []

    tasks.append(
        Signature(
            "batid.tasks.dl_source", args=["bdnb_2023_01", {"dpt": dpt}], immutable=True
        )
    )
    tasks.append(
        Signature(
            "batid.tasks.import_bdnb_addresses",
            args=[dpt],
            immutable=True,
        )
    )
    tasks.append(
        Signature(
            "batid.tasks.import_bdnb_bdgs",
            args=[dpt, bulk_launch_uuid],
            immutable=True,
        )
    )
    return tasks
