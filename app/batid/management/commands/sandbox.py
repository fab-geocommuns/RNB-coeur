from django.core.management.base import BaseCommand

from batid.models import Plot
from batid.services.imports.import_plots import import_etalab_plots
from batid.services.search_bdg import BuildingSearch


class Command(BaseCommand):
    def handle(self, *args, **options):
        # print("-- removing old plots")
        # Plot.objects.all().delete()
        #
        # print("-- importing plots")
        # import_etalab_plots("38")
        #
        # # ps = Plot.objects.filter(city__dpt="38")

        s = BuildingSearch()
        qs = s.get_queryset()

        for bdg in qs:
            print(bdg.rnb_id)
