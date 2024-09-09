from django.core.management.base import BaseCommand

from batid.services.guess_bdg_new import GeocodeAddressHandler


class Command(BaseCommand):
    def handle(self, *args, **options):

        address = " , 17390 Les Mathes"

        print(GeocodeAddressHandler._clean_address(address))

        pass
