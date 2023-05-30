from django.core.management.base import BaseCommand
import requests
from django.urls import get_resolver
from app.celery import app


class Command(BaseCommand):
    def handle(self, *args, **options):
        app.send_task("tasks.tmp_change_id_format")

        # base_url = "https://rnb-api.beta.gouv.fr"
        # # base_url = "http://localhost:800"
        #
        # r = requests.post(
        #     f"{base_url}/api/alpha/login/",
        #     data={"username": "paul", "password": "gggo"},
        # )
        #
        # print(r.status_code)
        # print(r.text)
