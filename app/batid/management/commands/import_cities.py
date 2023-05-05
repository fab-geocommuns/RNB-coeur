from datetime import datetime
from django.core.management.base import BaseCommand
from app.celery import app


class Command(BaseCommand):
    def handle(self, *args, **options):
        today = datetime.today().strftime("%Y-%m-%d")
        app.send_task("tasks.import_commune_insee", args=[today])
