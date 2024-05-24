# empty django command
import uuid

from celery import chain
from django.core.management.base import BaseCommand

from batid.management.commands.import_bdnb_dpt import (
    create_tasks_list as create_tasks_list_bdnb_dpt,
)
from batid.management.commands.import_bdtopo_dpt import (
    create_tasks_list as create_tasks_list_bdtopo_dpt,
)
from batid.management.commands.import_cities_dpt import (
    create_tasks_list as create_tasks_list_cities_dpt,
)
from batid.management.commands.import_plots_dpt import (
    create_tasks_list as create_tasks_list_plots_dpt,
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
        "bdtopo": create_tasks_list_bdtopo_dpt,
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


def dpt_list_metropole():
    return [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "2A",
        "2B",
        "21",
        "22",
        "23",
        "24",
        "25",
        "26",
        "27",
        "28",
        "29",
        "30",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
        "38",
        "39",
        "40",
        "41",
        "42",
        "43",
        "44",
        "45",
        "46",
        "47",
        "48",
        "49",
        "50",
        "51",
        "52",
        "53",
        "54",
        "55",
        "56",
        "57",
        "58",
        "59",
        "60",
        "61",
        "62",
        "63",
        "64",
        "65",
        "66",
        "67",
        "68",
        "69",
        "70",
        "71",
        "72",
        "73",
        "74",
        "75",
        "76",
        "77",
        "78",
        "79",
        "80",
        "81",
        "82",
        "83",
        "84",
        "85",
        "86",
        "87",
        "88",
        "89",
        "90",
        "91",
        "92",
        "93",
        "94",
        "95",
    ]


def dpt_list_overseas():
    return ["971", "972", "973", "974", "975", "976", "977", "978"]


def dpts_list():
    return dpt_list_metropole() + dpt_list_overseas()
