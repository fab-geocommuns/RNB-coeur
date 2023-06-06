from django.core.management.base import BaseCommand
from app.celery import app


class Command(BaseCommand):
    def handle(self, *args, **options):
        pass
