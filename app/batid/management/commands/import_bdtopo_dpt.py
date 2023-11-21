from datetime import datetime
from django.core.management.base import BaseCommand
from celery import chain, Signature


class Command(BaseCommand):
    help = "Import BDTOPO for a given departement (create candidates)"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt, bulk_launch_uuid=None):
    bdtopo_dpt = dpt.zfill(3)
    tasks = []
    tasks.append(
        Signature("batid.tasks.dl_source", args=["bdtopo", bdtopo_dpt], immutable=True)
    )
    tasks.append(
        Signature(
            "batid.tasks.import_bdtopo",
            args=[bdtopo_dpt],
            kwargs={"bulk_launch_uuid": bulk_launch_uuid},
            immutable=True,
        )
    )
    return tasks
