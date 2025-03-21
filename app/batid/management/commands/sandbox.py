from django.core.management.base import BaseCommand

from batid.services.source import Source
from batid.services.imports.import_bal import import_addresses


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        src = Source("ban")
        src.set_params({"dpt": "75"})

        src.download()
        src.uncompress()
