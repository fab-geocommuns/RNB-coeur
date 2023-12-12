import csv

import fiona
from django.core.management.base import BaseCommand

from batid.models import Building
from batid.services.candidate import Inspector
from batid.services.source import Source
from batid.services.imports.import_bdtopo import import_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **options):
        # import_bdtopo("bdtopo_2023_09", "38")
        i = Inspector()
        i.inspect_one()
        print("- Candidat -")
        print(i.candidate.id)
        print(i.candidate.source)
        print(i.candidate.source_version)
        print(i.candidate.source_id)
        print("> batiments")
        for b in i.matching_bdgs:
            print(b.rnb_id)
        print("> decision")
        print(i.candidate.inspection_details)

        if i.candidate.inspection_details["decision"] in ["creation", "update"]:
            print(">> Resulting building")
            b = Building.objects.get(rnb_id=i.candidate.inspection_details["rnb_id"])

            print(b.rnb_id)
            print(b.ext_ids)
