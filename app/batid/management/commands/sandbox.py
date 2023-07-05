import csv
import json

import psycopg2
from django.core.management.base import BaseCommand
from datetime import datetime, timezone

from django.db import connection

from batid.models import Candidate
from batid.services.source import Source


class Command(BaseCommand):
    def handle(self, *args, **options):
        addresses = [
            {
                "number": "1",
                "street": "RUE DE LA LIBERTE",
                "city": "PARIS",
                "zipcode": "75001",
                "insee": "75101",
            },
            {
                "number": "2",
                "street": "RUE DE L'IMPASSE",
                "city": "PARIS",
                "zipcode": "75001",
                "insee": "75101",
            },
        ]

        data = [
            {
                "shape": "MULTIPOLYGON (((411389.7 6375999.4,411401.8 6375987.7,411403.8 6375989.6,411408.7 6375984.4,411406.7 6375982.6,411414.4 6375973.3,411412.189217398 6375971.07109623,411382.083852432 6375991.36406477,411389.7 6375999.4)))",
                "source": "bdnb_7",
                "is_light": False,
                "source_id": "1",
                "addresses": json.dumps(addresses),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ]

        # Write it to csv
        src = Source(
            "sandbox",
            {
                "filename": "sandbox.csv",
            },
        )

        with open(src.path, "w") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=data[0].keys(),
                delimiter=";",
                quotechar="'",
                quoting=csv.QUOTE_NONE,
                escapechar="\\",
            )
            writer.writerows(data)

        with connection.cursor() as cursor, open(src.path, "r") as f:
            try:
                cursor.copy_from(f, "batid_candidate", sep=";", columns=data[0].keys())
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cursor.close()
                raise error

        c = Candidate.objects.all().order_by("-id")[0]

        print(c.addresses[1]["street"])
