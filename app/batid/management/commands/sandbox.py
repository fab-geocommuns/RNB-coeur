from celery.canvas import chain
from django.core.management.base import BaseCommand

from batid.services.imports.import_bdtopo import (
    create_bdtopo_dpt_import_tasks,
    bdtopo_src_params,
)
from batid.services.source import Source


class Command(BaseCommand):
    def handle(self, *args, **options):

        params = bdtopo_src_params("75", "2023-06-15")

        src = Source("bdtopo")
        src.set_params(params)

        print(src.uncompress_abs_dir)
