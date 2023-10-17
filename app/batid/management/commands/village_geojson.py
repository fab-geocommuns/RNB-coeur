from django.core.management.base import BaseCommand

from batid.services.export.village import export_village


class Command(BaseCommand):
    def handle(self, *args, **options):
        export_village()
