from pprint import pprint

from django.core.management.base import BaseCommand
from batid.models import Building

class Command(BaseCommand):


    def handle(self, *args, **options):

        Building.objects.all().delete()











