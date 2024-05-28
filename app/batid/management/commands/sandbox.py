from django.core.management.base import BaseCommand

from batid.services.source import bdtopo_src_params
from batid.tasks import import_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **options):

        src_params = bdtopo_src_params("38", "2024-03-15")
        import_bdtopo(src_params)
