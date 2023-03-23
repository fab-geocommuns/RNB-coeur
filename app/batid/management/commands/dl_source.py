from pprint import pprint

from django.core.management.base import BaseCommand
from batid.logic.source import Source


class Command(BaseCommand):

    # Add arguments to the command
    def __init__(self):
        super().__init__()

        self.src = None

    def add_arguments(self, parser):
        parser.add_argument('src', type=str)
        parser.add_argument('dpt', type=str)
        pass

    def handle(self, *args, **options):

        self.src = Source(options['src'])
        self.src.set_param('dpt', options['dpt'])

        self.download()
        self.unzip()

    def download(self):

        self.src.download()
        self.src.uncompress()

    def unzip(self):

        pass











