from django.core.management.base import BaseCommand

from batid.services.source import bdtopo_src_params
from batid.tasks import import_bdtopo
from batid.services.geocoders import BanBatchGeocoder
from batid.services.guess_bdg_new import Guesser


class Command(BaseCommand):
    def handle(self, *args, **options):
      pass
