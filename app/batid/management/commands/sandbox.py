from django.core.management.base import BaseCommand
from batid.services.candidate import Inspector


class Command(BaseCommand):
    def handle(self, *args, **options):
        i_class = Inspector
        i_class.BATCH_SIZE = 1000

        i = i_class()
        i.inspect()
