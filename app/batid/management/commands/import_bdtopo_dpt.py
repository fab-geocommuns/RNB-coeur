from datetime import datetime
from django.core.management.base import BaseCommand
from celery import chain, Signature

from batid.services.source import bdtopo_source_switcher


class Command(BaseCommand):
    help = "Import BDTOPO for a given departement (create candidates)"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt, bulk_launch_uuid=None):
    bdtopo_dpt = dpt.zfill(3)

    bdtopo_edition = "bdtopo_2023_09"

    source_name = bdtopo_source_switcher(bdtopo_edition, bdtopo_dpt)

    tasks = []
    tasks.append(
        Signature(
            "batid.tasks.dl_source", args=[source_name, bdtopo_dpt], immutable=True
        )
    )
    tasks.append(
        Signature(
            "batid.tasks.import_bdtopo",
            args=[bdtopo_dpt, bdtopo_edition, bulk_launch_uuid],
            immutable=True,
        )
    )
    return tasks
