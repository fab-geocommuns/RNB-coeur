# empty django command
from celery import chain, Signature
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import data for a departement"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)
        parser.add_argument("--steps", type=str, default="all")

    def handle(self, *args, **options):
        # ###########
        # Departement
        dpt = options["dpt"]
        bdtopo_dpt = dpt.zfill(
            3
        )  # BD Topo departements are zero-prefixed 3 digits codes.
        bdnb_dpt = dpt.lower()

        # ###########
        # Steps
        all_steps = [
            "import_cities",
            "dl_bdtopo",
            "dl_bdnb7",
            "import_bdtopo",
            "import_bdnb7",
            "pre_clean_candidates",
            "inspect",
            "add_status",
        ]
        steps = all_steps if options["steps"] == "all" else options["steps"].split(",")

        # ###########
        # Define tasks to send to celery

        print("Sending tasks to celery")
        print(steps)

        tasks = []

        if "import_cities" in steps:
            tasks.append(
                Signature("batid.tasks.import_cities", args=[dpt], immutable=True)
            )

        if "dl_bdtopo" in steps:
            tasks.append(
                Signature(
                    "batid.tasks.dl_source", args=["bdtopo", bdtopo_dpt], immutable=True
                )
            )
        if "dl_bdnb7" in steps:
            tasks.append(
                Signature(
                    "batid.tasks.dl_source", args=["bdnb_7", bdnb_dpt], immutable=True
                )
            )
        if "import_bdtopo" in steps:
            tasks.append(
                Signature(
                    "batid.tasks.import_bdtopo", args=[bdtopo_dpt], immutable=True
                )
            )
        if "import_bdnb7" in steps:
            tasks.append(
                Signature("batid.tasks.import_bdnb7", args=[bdnb_dpt], immutable=True)
            )
        if "pre_clean_candidates" in steps:
            tasks.append(
                Signature("batid.tasks.remove_inspected_candidates", immutable=True)
            )
            tasks.append(
                Signature("batid.tasks.remove_invalid_candidates", immutable=True)
            )
        if "inspect" in steps:
            tasks.append(Signature("batid.tasks.inspect_candidates", immutable=True))
        if "add_status" in steps:
            tasks.append(Signature("batid.tasks.add_default_status", immutable=True))

        # Send the tasks
        if len(tasks) > 0:
            chain(*tasks)()
