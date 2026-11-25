# empty django command
from batid.services.administrative_areas import dpts_list
from batid.services.data_gouv_publication import check_run_id
from django.core.management.base import BaseCommand, CommandError

from app.celery import app


class Command(BaseCommand):
    help = "Publish opendata for each department or full France"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strate",
            type=str,
            default="department",
            choices=["country", "department"],
        ),
        parser.add_argument(
            "--start-dpt",
            type=str,
            help="Only for strate=department, allow to start at a specific department code.",
        )
        parser.add_argument(
            "--run-id",
            type=str,
            help="Only for strate=country: relaunch the national file of a run from the department archives its failure kept in data/datagouvfr_run_<run id>.",
        )

    def handle(self, *args, **options):
        strate = options["strate"]
        starting_code = options.get("start_dpt", None)
        run_id = options.get("run_id", None)
        if run_id is not None:
            if strate != "country":
                raise CommandError("--run-id is only accepted with --strate country")
            try:
                check_run_id(run_id)
            except ValueError as e:
                raise CommandError(str(e)) from e
        enqueue_tasks(strate=strate, starting_code=starting_code, run_id=run_id)


def enqueue_tasks(*, strate, starting_code=None, run_id=None):
    if strate == "country":
        app.send_task(
            "batid.tasks.publish_datagouv_national", kwargs={"run_id": run_id}
        )
    elif strate == "department":
        dpts = dpts_list()

        if starting_code is not None:
            dpts = dpts[dpts.index(starting_code) :]

        for dept in dpts:
            app.send_task("batid.tasks.publish_datagouv_dpt", args=[dept])
