from django.core.management.base import BaseCommand

from batid.models import Address
from batid.services.candidate import Inspector
from batid.services.imports.import_bdnb7 import import_bdnb7_addresses


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Address.objects.all().delete()

        import_bdnb7_addresses("33")

        # i_class = Inspector
        # i_class.BATCH_SIZE = 1000
        #
        # i = i_class()
        # i.inspect()
