from django.core.management.base import BaseCommand

from app.celery import app


class Command(BaseCommand):
    help = "Remove all buildings from departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):
        # ###########
        # Departement
        dpt = options["dpt"]

        confirm = input(f"Type 'REMOVE{dpt}' to confirm: ")

        if confirm != f"REMOVE{dpt}":
            print("Aborting")
            return

        app.send_task("batid.tasks.remove_dpt_bdgs", args=[dpt])
        print("Task sent to the worker")
