from django.core.management.base import BaseCommand
import requests
from django.urls import get_resolver
from app.celery import app
from batid.tasks import test_all


class Command(BaseCommand):
    def handle(self, *args, **options):
        t = app.send_task("batid.tasks.test_all")
        print(t)

        # test_all.apply_async()

        # app.send_task("tasks.tmp_change_id_format")
