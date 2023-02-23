from pprint import pprint

from django.core.management.base import BaseCommand
from batid.logic.building import generate_id

class Command(BaseCommand):


    def handle(self, *args, **options):

        ids = []
        for i in range(23_000_000):

            id = generate_id()
            ids.append(id)


        unique_ids = set(ids)

        self.stdout.write(self.style.SUCCESS(f'Generated {len(ids)} ids'))
        self.stdout.write(self.style.SUCCESS(f'Unique ids: {len(unique_ids)}'))











