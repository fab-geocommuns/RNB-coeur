import csv
from io import StringIO

import requests

from batid.models import DiffusionDatabase


def run(self, *args):
    print(args)
    csv_url = args[0]
    target_database_id = args[1]

    target_database = DiffusionDatabase.objects.get(id=int(target_database_id))

    try:
        response = requests.get(csv_url)
        response.encoding = response.apparent_encoding
        response.raise_for_status()

        csv_file = StringIO(response.text)
        reader = csv.DictReader(csv_file)

        attributes = []
        for row in reader:
            attributes.append(row)

        target_database.attributes = attributes
        target_database.save()

        print(f"Successfully imported {len(attributes)} attributes.")

    except requests.RequestException as e:
        print(f"Failed to fetch CSV: {e}")
    except Exception as e:
        print(f"Error processing CSV: {e}")
