import csv
import requests
from io import StringIO
from batid.models import DiffusionDatabase


def str_to_bool(value):
    return value.strip().lower() in ("true", "1", "yes")


def list_to_array(value):
    return value.split(",")


def run(self, *args):
    print(args)
    csv_url = args[0]

    try:
        response = requests.get(csv_url)
        response.encoding = response.apparent_encoding
        response.raise_for_status()

        csv_file = StringIO(response.text)
        reader = csv.DictReader(csv_file)
        rows = []
        for row in reader:
            row["is_featured"] = str_to_bool(row["is_featured"])
            row["tags"] = list_to_array(row["tags"])
            rows.append(row)
        records = [DiffusionDatabase(**row) for row in rows]

        DiffusionDatabase.objects.bulk_create(records)

        print(f"Successfully imported {len(records)} rows.")

    except requests.RequestException as e:
        print(f"Failed to fetch CSV: {e}")
    except Exception as e:
        print(f"Error processing CSV: {e}")
