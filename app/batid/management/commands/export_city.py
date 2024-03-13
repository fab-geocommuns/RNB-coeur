from django.core.management.base import BaseCommand

from app.celery import app


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("city", type=str)

    def handle(self, *args, **options):
        app.send_task("batid.tasks.export_city", args=[options["city"]])
