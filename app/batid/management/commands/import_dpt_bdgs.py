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
            print("Sending tasks to celery")
            print(steps)
            chain(*tasks)()


def steps_list():
    return [
        "inspect",
        "add_status",
    ]


def create_tasks_list(dpt, steps="all"):
    bdtopo_dpt = dpt.zfill(3)  # BD Topo departements are zero-prefixed 3 digits codes.
    bdnb_dpt = dpt.lower()

    all_steps = steps_list()
    steps = all_steps if steps == "all" else steps.split(",")

    # ###########
    # Define tasks to send to celery
    tasks = []

    if "inspect" in steps:
        tasks.append(Signature("batid.tasks.inspect_candidates", immutable=True))
    if "add_status" in steps:
        tasks.append(Signature("batid.tasks.add_default_status", immutable=True))

    return tasks
