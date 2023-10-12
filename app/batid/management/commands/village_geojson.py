from django.core.management.base import BaseCommand
from app.celery import app
from batid.tests.test_village import create_village


class Command(BaseCommand):
    def handle(self, *args, **options):
        create_village()
