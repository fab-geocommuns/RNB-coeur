from django.test import TestCase
from batid.management.commands.import_france import create_tasks_list_france
from batid.management.commands.import_dpt_bdgs import (
    steps_list as import_buildings_steps_list,
)


class ImportFranceTestCase(TestCase):
    def test_create_tasks_from_1_buildings(self):
        # create tasks for buildings import
        # create tasks when starting from the first dpt
        # There are 97 departements in France, excluding overseas territories
        tasks = create_tasks_list_france("01", "buildings")
        self.assertEqual(len(tasks), 96 * len(import_buildings_steps_list()))

        tasks = create_tasks_list_france("", "buildings")
        self.assertEqual(len(tasks), 96 * len(import_buildings_steps_list()))

    def test_create_tasks_from_custom_buildings(self):
        tasks = create_tasks_list_france("90", "buildings")
        # expected tasks for 6 departements (90 to 95)
        print(tasks)
        self.assertEqual(len(tasks), 6 * len(import_buildings_steps_list()))

    def test_create_tasks_from_1_cities(self):
        # create tasks for cities import
        tasks = create_tasks_list_france("01", "cities")
        self.assertEqual(len(tasks), 96)

        tasks = create_tasks_list_france("", "cities")
        self.assertEqual(len(tasks), 96)

    def test_create_tasks_from_1_plots(self):
        # create tasks for plots import
        # there are 2 tasks per departement : dl_source and import_plots
        tasks = create_tasks_list_france("01", "plots")
        self.assertEqual(len(tasks), 96 * 2)

        tasks = create_tasks_list_france("", "plots")
        self.assertEqual(len(tasks), 96 * 2)
