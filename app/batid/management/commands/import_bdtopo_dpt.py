from celery import chain
from celery import Signature
from django.core.management.base import BaseCommand

from batid.services.source import bdtopo_src_params


class Command(BaseCommand):
    help = "Import BDTOPO for a given departement (create candidates)"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt, bulk_launch_uuid=None):

    # todo : créer un sélecteur de date automatique
    most_recent_date = "2024-03-15"

    src_params = bdtopo_src_params(dpt, most_recent_date)

    tasks = []
    tasks.append(
        Signature("batid.tasks.dl_source", args=["bdtopo", src_params], immutable=True)
    )
    tasks.append(
        Signature(
            "batid.tasks.import_bdtopo",
            args=[bdtopo_dpt, bdtopo_edition, bulk_launch_uuid],
            immutable=True,
        )
    )
    return tasks
