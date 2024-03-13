from django.core.management.base import BaseCommand

from batid.services.guess_bdg_new import Guesser
from batid.utils.misc import is_float
import json
import requests

class Command(BaseCommand):
    def handle(self, *args, **options):
        pass
