from django.core.management.base import BaseCommand

from batid.services.imports.import_bal import import_addresses


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        import_addresses({"dpt": "33"})
