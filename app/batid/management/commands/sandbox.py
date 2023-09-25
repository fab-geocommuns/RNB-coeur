from django.core.management.base import BaseCommand
from batid.services.imports.import_plots import import_etalab_plots


class Command(BaseCommand):
    def handle(self, *args, **options):
        import_etalab_plots("38")
