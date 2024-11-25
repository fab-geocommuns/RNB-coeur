from django.core.management.base import BaseCommand

from batid.models import Building
from batid.models import Department
from batid.services.administrative_areas import dpts_list


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--dpt", type=str, default="all")

    def handle(self, *args, **options):
        codes = dpts_list() if options["dpt"] == "all" else options["dpt"].split(",")

        for code in codes:
            dpt = Department.objects.get(code=code)

            bdg_count = Building.objects.filter(point__intersects=dpt.shape).count()
            print(f"{dpt.code} - {dpt.name} - Building : {bdg_count}")
