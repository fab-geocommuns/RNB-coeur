import cProfile
import io
import pstats

from django.core.management.base import BaseCommand
import fiona
from batid.services.source import Source

from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        pass
