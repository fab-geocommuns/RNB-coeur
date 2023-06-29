from time import perf_counter

from batid.models import Candidate, Building
from django.core.management.base import BaseCommand

from batid.services.building import add_default_status
from batid.services.candidate import Inspector
from batid.services.vector_tiles import generate_all_tiles


class Command(BaseCommand):
    def handle(self, *args, **options):
        generate_all_tiles()
