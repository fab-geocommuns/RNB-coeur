from django.core.management.base import BaseCommand
import requests


class Command(BaseCommand):
    def handle(self, *args, **options):
        data = {
            "issue_number": "ADS-TEST-NEW-BDG",
            "issue_date": "2019-03-18",
            "insee_code": "4242",
            "buildings_operations": [
                {
                    "operation": "build",
                    "building": {
                        "rnb_id": "new",
                        "lat": 44.7802149854455,
                        "lng": -0.4617233264741004,
                    },
                }
            ],
        }

        r = requests.post(
            "http://localhost:8000/api/alpha/ads/",
            json=data,
            headers={"Authorization": "Token 8b105f00bb8597ae2e604eeec5263f9db1d8d813"},
        )

        # LOCAL
        # r = requests.post(
        #     "http://localhost:8000/api/alpha/ads/",
        #     json=data,
        #     headers={"Authorization": "Token 25343c752b349f2b65691f3d67857ad886eea07a"},
        # )

        print(r.status_code)
        print(r.content)
