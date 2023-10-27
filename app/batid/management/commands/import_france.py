# empty django command
from celery import chain
from django.core.management.base import BaseCommand
from batid.management.commands.import_dpt_bdgs import (
    create_tasks_list as create_tasks_list_bdgs_dpt,
)
from batid.management.commands.import_cities_dpt import (
    create_tasks_list as create_tasks_list_cities_dpt,
)
from batid.management.commands.import_plots_dpt import (
    create_tasks_list as create_tasks_list_plots_dpt,
)
from batid.management.commands.import_bdnb_dpt import (
    create_tasks_list as create_tasks_list_bdnb_dpt,
)


class Command(BaseCommand):
    help = (
        "Import data for France by calling successively an import for each departement"
    )

    def add_arguments(self, parser):
        parser.add_argument("task", type=str)
        parser.add_argument("--start-dpt", type=str, default="01")

    def handle(self, *args, **options):
        start_dpt = options["start_dpt"]
        task_name = options["task"]
        tasks = create_tasks_list_france(start_dpt, task_name)
        chain(*tasks)()


def task_method(task_name):
    d = {
        "cities": create_tasks_list_cities_dpt,
        "plots": create_tasks_list_plots_dpt,
        "bdnb": create_tasks_list_bdnb_dpt,
    }
    return d[task_name]


def create_tasks_list_france(start_dpt, task_name):
    tasks = []
    dpts = dpts_list()
    # find start_dpt index in dpts list. Return 0 if not found
    start_dpt_index = dpts.index(start_dpt) if start_dpt in dpts else 0
    create_task_method = task_method(task_name)

    for dpt in dpts[start_dpt_index:]:
        tasks.append(create_task_method(dpt))
    # flattern the list
    tasks = [item for sublist in tasks for item in sublist]
    return tasks


def dpts_list():
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
