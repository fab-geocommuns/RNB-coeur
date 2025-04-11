import csv
import os

import requests
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Parse a CSV file and create tokens for the users"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="CSV file to parse")

    def handle(self, *args, **kwargs):
        csv_file = kwargs["csv_file"]
        users = []

        with open(csv_file, newline="") as file:
            reader = csv.reader(file, delimiter=";")
            for idx, row in enumerate(list(reader)):

                if idx == 0:
                    # Skip the header row
                    continue

                # Edit this part depending on your CSV file structure
                username = row[3]
                email = row[3]
                organization_name = row[4]
                organization_managed_cities = [
                    f"{city.zfill(5)}" for city in row[5].split(",")
                ]

                user = {
                    "username": username,
                    "email": email,
                    "organization_name": organization_name,
                    "organization_managed_cities": organization_managed_cities,
                }
                users.append(user)

        self.stdout.write(f"Parsed {len(users)} users :\n")

        for user in users:
            print("--")
            print(f"Username: {user['username']}")
            print(f"Email: {user['email']}")
            print(f"Organization name: {user['organization_name']}")
            print(f"Managed cities: {', '.join(user['organization_managed_cities'])}")
        # User must confirm creation

        print("----------- Confirm -----------")
        self.stdout.write(
            f"Do you want to create tokens for those {len(users)} users? (y/n)"
        )
        confirm = input().strip().lower()
        if confirm != "y":
            self.stdout.write("Aborting...")
            return

        print(f"Sending {len(users)} users to the API\n")
        response = requests.post(
            "https://rnb-api.beta.gouv.fr/api/alpha/ads/token/",
            json=users,
            headers={"Authorization": f'Token {os.getenv("USER_TOKEN")}'},
        )

        if response.status_code == 200:
            created_users = response.json().get("created_users", [])
            writer = csv.writer(self.stdout)
            writer.writerow(["username", "email", "organization_name", "token"])
            for user in created_users:
                writer.writerow(
                    [
                        user["username"],
                        user["email"],
                        user["organization_name"],
                        user["token"],
                    ]
                )
        else:
            self.stderr.write(
                f"Error during API call: {response.status_code} - {response.text}"
            )
