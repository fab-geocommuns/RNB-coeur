# empty django command
import uuid

from celery import chain
from django.core.management.base import BaseCommand

from batid.management.commands.import_bdnb_dpt import (
    create_tasks_list as create_tasks_list_bdnb_dpt,
)
from batid.management.commands.import_cities_dpt import (
    create_tasks_list as create_tasks_list_cities_dpt,
)
from batid.management.commands.import_plots_dpt import (
    create_tasks_list as create_tasks_list_plots_dpt,
)
from batid.services.france import dpt_list_metropole
from batid.services.france import dpts_list
from batid.services.imports.import_bdtopo import (
    create_bdtopo_full_import_tasks,
)


class Command(BaseCommand):
    help = (
        "Import data for France by calling successively an import for each departement"
    )

    def add_arguments(self, parser):
        parser.add_argument("task", type=str)
        parser.add_argument("--start-dpt", type=str, default="01")
        parser.add_argument("--end-dpt", type=str, default="95")

    def handle(self, *args, **options):
        start_dpt = options["start_dpt"]
        end_dpt = options["end_dpt"]
        task_name = options["task"]
        tasks = create_tasks_list_france(start_dpt, end_dpt, task_name)
        chain(*tasks)()


def task_method(task_name):
    d = {
        "cities": create_tasks_list_cities_dpt,
        "plots": create_tasks_list_plots_dpt,
        "bdnb": create_tasks_list_bdnb_dpt,
        "bdtopo": create_bdtopo_full_import_tasks,
    }
    return d[task_name]


def task_dpt_list(task_name):
    d = {
        "cities": dpt_list_metropole(),
        "plots": dpt_list_metropole(),
        "bdnb": dpt_list_metropole(),
        "bdtopo": dpts_list(),
    }
    return d[task_name]


def create_tasks_list_france(start_dpt, end_dpt, task_name):
    tasks = []
    dpts = task_dpt_list(task_name)
    # find start_dpt index in dpts list. Return 0 if not found
    start_dpt_index = dpts.index(start_dpt) if start_dpt in dpts else 0
    end_dpt_index = dpts.index(end_dpt) + 1 if start_dpt in dpts else len(dpts)
    create_task_method = task_method(task_name)
    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpts[start_dpt_index:end_dpt_index]:
        if task_name in ["bdnb", "bdtopo"]:
            tasks.append(create_task_method(dpt, bulk_launch_uuid))
        else:
            tasks.append(create_task_method(dpt))
    # flattern the list
    tasks = [item for sublist in tasks for item in sublist]
    return tasks
