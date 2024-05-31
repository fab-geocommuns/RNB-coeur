from pprint import pprint


from celery.canvas import Signature, chain
from django.core.management.base import BaseCommand


from batid.services.imports.import_bdtopo import create_bdtopo_dpt_import_tasks


class Command(BaseCommand):
    def handle(self, *args, **options):

        tasks = create_bdtopo_dpt_import_tasks("48")
        chain(*tasks)()
