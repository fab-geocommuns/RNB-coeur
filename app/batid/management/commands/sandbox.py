from django.core.management.base import BaseCommand

from batid.models import Address, Candidate
from batid.services.candidate import Inspector
from batid.services.imports.import_bdnb7 import (
    import_bdnb7_addresses,
    import_bdnb7_bdgs,
)


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Candidate.objects.all().delete()
        # import_bdnb7_bdgs("33")

        i_class = Inspector
        i_class.BATCH_SIZE = 10000

        i = i_class()
        i.inspect()
