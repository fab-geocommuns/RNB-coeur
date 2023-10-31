from django.core.management.base import BaseCommand
from app.celery import app


class Command(BaseCommand):
    help = "Inspect candidates created by previous imports. And eventually create buildings from candidates."

    def handle(self, *args, **options):
        app.send_task("batid.tasks.inspect_candidates")
