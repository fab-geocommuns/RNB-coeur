from celery import chain
from celery import Signature
from django.core.management.base import BaseCommand

from batid.services.source import bdtopo_release_before
from batid.services.source import bdtopo_src_params


class Command(BaseCommand):
    help = "Import BDTOPO for a given departement (create candidates)"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()
