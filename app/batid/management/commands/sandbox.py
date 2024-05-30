from celery.canvas import Signature, chain
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):

        tasks = []
        tasks.append(
            Signature("batid.tasks.queue_full_bdtopo_import", args=[], immutable=True)
        )

        chain(*tasks)()

        pass
