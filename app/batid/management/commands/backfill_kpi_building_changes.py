from datetime import date, timedelta

from batid.models import KPI
from batid.services.kpi import (
    KPI_BUILDING_CHANGES_CONTRIBUTIONS,
    KPI_BUILDING_CHANGES_IMPORT_BAL,
    KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
    count_building_changes_daily,
)
from django.core.management.base import BaseCommand


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
            daily_changes = count_building_changes_daily(d)
            bdtopo_count = daily_changes["import_bdtopo"]
            bal_count = daily_changes["import_bal"]
            contributions_count = daily_changes["contributions"]

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
