from typing import Optional

from batid.services.imports.import_plots import (
    create_plots_full_import_tasks,
    etalab_recent_release_date,
)
from celery import chain
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import plots (cadastre) for a given departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        tasks = create_tasks_list(options["dpt"])
        chain(*tasks)()


def create_tasks_list(dpt, *, release_date: Optional[str] = None):
    return create_plots_full_import_tasks(
        dpt_list=[dpt], release_date=release_date or etalab_recent_release_date()
    )
