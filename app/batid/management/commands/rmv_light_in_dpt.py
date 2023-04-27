import argparse

from celery import chain, Signature
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Remove light buildings from departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)
        parser.add_argument(
            "--skip_dl", action=argparse.BooleanOptionalAction, default=False
        )

    def handle(self, *args, **options):
        # ###########
        # Departement
        dpt = options["dpt"]
        # BD Topo departements are zero-prefixed 3 digits codes.
        bdtopo_dpt = dpt.zfill(3)

        tasks = []

        if not options["skip_dl"]:
            tasks.append(
                Signature(
                    "tasks.dl_source", args=["bdtopo", bdtopo_dpt], immutable=True
                )
            )

        tasks.append(Signature("tasks.remove_light_bdgs", args=[dpt], immutable=True))

        chain(*tasks)()
