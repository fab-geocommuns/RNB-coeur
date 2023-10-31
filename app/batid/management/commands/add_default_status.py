from django.core.management.base import BaseCommand
from app.celery import app


class Command(BaseCommand):
    help = "Add a default status (constructed) to buildings without status"

    def handle(self, *args, **options):
        app.send_task("add_default_status")
