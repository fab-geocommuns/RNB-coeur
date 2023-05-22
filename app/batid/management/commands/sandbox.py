from django.core.management.base import BaseCommand
import requests
from django.urls import get_resolver


class Command(BaseCommand):
    def handle(self, *args, **options):
        print(get_resolver().url_patterns)

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
