from django.core.management.base import BaseCommand
from batid.list_bdg import public_bdg_queryset


class Command(BaseCommand):
    def handle(self, *args, **options):
        qs = public_bdg_queryset()

        print(qs[:20].query)
