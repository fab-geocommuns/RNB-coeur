from django.core.management.base import BaseCommand

from app.celery import app


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("insee_codes", type=str)

    def handle(self, *args, **options):
        for code in options["insee_codes"].split(","):
            t = app.send_task("batid.tasks.export_city", args=[code])
            print(t)
