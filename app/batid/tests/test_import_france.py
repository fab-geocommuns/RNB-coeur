from django.test import TestCase
from batid.management.commands.import_france import create_tasks_list_france
from batid.management.commands.import_dpt_bdgs import (
    steps_list as import_buildings_steps_list,
)


class ImportFranceTestCase(TestCase):
    def test_create_tasks_from_1_cities(self):
        # create tasks for cities import
        tasks = create_tasks_list_france("01", "cities")
        self.assertEqual(len(tasks), 96)

        tasks = create_tasks_list_france("", "cities")
        self.assertEqual(len(tasks), 96)

    def test_create_tasks_buildings_from_custom_start_dpt(self):
        tasks = create_tasks_list_france("90", "cities")
        # expected tasks for 6 departements (90 to 95)
        print(tasks)
        self.assertEqual(len(tasks), 6)

    def test_create_tasks_from_1_plots(self):
        # create tasks for plots import
        # there are 2 tasks per departement : dl_source and import_plots
        tasks = create_tasks_list_france("01", "plots")
        self.assertEqual(len(tasks), 96 * 2)

        tasks = create_tasks_list_france("", "plots")
        self.assertEqual(len(tasks), 96 * 2)

    def test_create_tasks_from_1_bdnb(self):
        # create tasks for bdnb import
        # there are 3 tasks per departement : dl_source and import_addresses and import_bdgs
        tasks = create_tasks_list_france("01", "bdnb")
        self.assertEqual(len(tasks), 96 * 3)
