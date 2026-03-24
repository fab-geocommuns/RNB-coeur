from datetime import date
from datetime import timedelta

from django.core.management.base import BaseCommand

from batid.models import KPI
from batid.services.kpi import count_building_changes_contributions
from batid.services.kpi import count_building_changes_import_bal
from batid.services.kpi import count_building_changes_import_bdtopo
from batid.services.kpi import KPI_BUILDING_CHANGES_CONTRIBUTIONS
from batid.services.kpi import KPI_BUILDING_CHANGES_IMPORT_BAL
from batid.services.kpi import KPI_BUILDING_CHANGES_IMPORT_BDTOPO


class Command(BaseCommand):
    help = "Backfill daily building change KPIs"

    def add_arguments(self, parser):
        parser.add_argument("--since", type=str, default="2023-12-01")
        parser.add_argument("--until", type=str, default=date.today().isoformat())

    def handle(self, *args, **options):
        since = date.fromisoformat(options["since"])
        until = date.fromisoformat(options["until"])

        print(f"Backfilling building change KPIs from {since} to {until}")

        d = since
        while d <= until:
            bdtopo_count = count_building_changes_import_bdtopo(d)
            bal_count = count_building_changes_import_bal(d)
            contributions_count = count_building_changes_contributions(d)

            KPI.objects.update_or_create(
                name=KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
                value_date=d,
                defaults={"value": bdtopo_count},
            )
            KPI.objects.update_or_create(
                name=KPI_BUILDING_CHANGES_IMPORT_BAL,
                value_date=d,
                defaults={"value": bal_count},
            )
            KPI.objects.update_or_create(
                name=KPI_BUILDING_CHANGES_CONTRIBUTIONS,
                value_date=d,
                defaults={"value": contributions_count},
            )

            print(
                f"{d} | bdtopo={bdtopo_count} bal={bal_count} contributions={contributions_count}"
            )
            d += timedelta(days=1)

        print("Done")
