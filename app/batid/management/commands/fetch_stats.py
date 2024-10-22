from django.core.management.base import BaseCommand

from app.celery import app
from batid.services.stats import fetch_stats, get_path


class Command(BaseCommand):

    def handle(self, *args, **options):

        print('Fetching stats...')
        fetch_stats()
        print('Done.')
        print(f"Stats have been saved in {get_path()}")

