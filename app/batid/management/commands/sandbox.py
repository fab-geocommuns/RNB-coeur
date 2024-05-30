from celery.canvas import Signature, chain
from django.core.management.base import BaseCommand

from batid.services.imports.import_bdtopo import (
    create_bdtopo_dpt_import_tasks,
    create_bdtopo_full_import_tasks,
)


class Command(BaseCommand):
    def handle(self, *args, **options):

        tasks = []
        tasks.append(
            Signature("batid.tasks.queue_full_bdtopo_import", args=[], immutable=True)
        )

        # tasks = create_bdtopo_dpt_import_tasks("01")

        chain(*tasks)()
