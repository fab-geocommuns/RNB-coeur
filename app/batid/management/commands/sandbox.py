from django.core.management.base import BaseCommand

from batid.services.guess_bdg_new import Guesser


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        pass
