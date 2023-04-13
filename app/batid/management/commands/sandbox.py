from django.core.management.base import BaseCommand
from rnbid.generator import generate_id


class Command(BaseCommand):
    def handle(self, *args, **options):
        division_by_zero = 1 / 0
