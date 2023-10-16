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
        steps = options["steps"]

        tasks = create_tasks_list(dpt, steps)

        # Send the tasks
        if len(tasks) > 0:
            chain(*tasks)()


def create_tasks_list(dpt, steps):
    bdtopo_dpt = dpt.zfill(3)  # BD Topo departements are zero-prefixed 3 digits codes.
    bdnb_dpt = dpt.lower()

    # ###########
    # Steps
    all_steps = [
        "import_cities",
        "dl_bdtopo",
        "dl_bdnb7",
        "dl_plots",
        "import_bdtopo",
        "import_bdnb7_addresses",
        "import_bdnb7_bdgs",
        "import_plots",
        "pre_clean_candidates",
        "inspect",
        "add_status",
    ]
    steps = all_steps if steps == "all" else steps.split(",")

    # ###########
    # Define tasks to send to celery

    print("Sending tasks to celery")
    print(steps)

    tasks = []

    if "import_cities" in steps:
        tasks.append(Signature("batid.tasks.import_cities", args=[dpt], immutable=True))

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
    if "dl_plots" in steps:
        tasks.append(
            Signature("batid.tasks.dl_source", args=["plot", dpt], immutable=True)
        )
    if "import_bdtopo" in steps:
        tasks.append(
            Signature("batid.tasks.import_bdtopo", args=[bdtopo_dpt], immutable=True)
        )
    if "import_bdnb7_addresses" in steps:
        tasks.append(
            Signature(
                "batid.tasks.import_bdnb7_addresses",
                args=[bdnb_dpt],
                immutable=True,
            )
        )
    if "import_bdnb7_bdgs" in steps:
        tasks.append(
            Signature("batid.tasks.import_bdnb7_bdgs", args=[bdnb_dpt], immutable=True)
        )
    if "import_plots" in steps:
        tasks.append(Signature("batid.tasks.import_plots", args=[dpt], immutable=True))
    if "pre_clean_candidates" in steps:
        # This task is commented out because inspected candidates are removed during the inspection
        # tasks.append(
        #     Signature("batid.tasks.remove_inspected_candidates", immutable=True)
        # )
        tasks.append(Signature("batid.tasks.remove_invalid_candidates", immutable=True))
    if "inspect" in steps:
        tasks.append(Signature("batid.tasks.inspect_candidates", immutable=True))
    if "add_status" in steps:
        tasks.append(Signature("batid.tasks.add_default_status", immutable=True))

    return tasks
