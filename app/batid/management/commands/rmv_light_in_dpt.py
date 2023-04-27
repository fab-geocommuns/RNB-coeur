from celery import chain, Signature
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Remove light buildings from departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        # ###########
        # Departement
        dpt = options["dpt"]
        # BD Topo departements are zero-prefixed 3 digits codes.
        bdtopo_dpt = dpt.zfill(3)

        chain(
            Signature("tasks.dl_source", args=["bdtopo", bdtopo_dpt], immutable=True),
            Signature("tasks.remove_light_bdgs", args=[dpt], immutable=True),
        )()
