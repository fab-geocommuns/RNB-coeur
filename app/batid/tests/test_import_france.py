from collections import Counter

from django.test import TestCase

from batid.management.commands.import_france import create_tasks_list_france
from batid.management.commands.import_france import dpt_list_metropole


class ImportFranceTestCase(TestCase):
    def test_create_tasks_from_1_cities(self):
        # create tasks for cities import
        tasks = create_tasks_list_france("01", "95", "cities")
        self.assertEqual(len(tasks), len(dpt_list_metropole()))

        tasks = create_tasks_list_france("", "777", "cities")
        self.assertEqual(len(tasks), len(dpt_list_metropole()))

    def test_create_tasks_buildings_from_custom_start_dpt(self):
        tasks = create_tasks_list_france("90", "95", "cities")
        # expected tasks for 6 departements (90 to 95)
        self.assertEqual(len(tasks), 6)

    def test_create_tasks_buildings_from_custom_start_end_dpt(self):
        tasks = create_tasks_list_france("90", "90", "cities")
        # expected tasks for 1 departement (90)
        self.assertEqual(len(tasks), 1)

    def test_create_tasks_from_1_plots(self):
        # create tasks for plots import
        # there are 2 tasks per departement : dl_source and import_plots
        tasks = create_tasks_list_france("01", "95", "plots")
        self.assertEqual(len(tasks), len(dpt_list_metropole()) * 2)

        tasks = create_tasks_list_france("", "", "plots")
        self.assertEqual(len(tasks), len(dpt_list_metropole()) * 2)

    def test_create_tasks_from_1_bdnb(self):
        # create tasks for bdnb import
        # there are 3 tasks per departement : dl_source and import_addresses and import_bdgs
        tasks = create_tasks_list_france("01", "95", "bdnb")
        self.assertEqual(len(tasks), len(dpt_list_metropole()) * 3)

        import_buildings_tasks_uuid = [
            t.args[1] for t in tasks if t.name == "batid.tasks.import_bdnb_bdgs"
        ]
        counter = Counter(import_buildings_tasks_uuid)
        # A unique UUID is created for all the tasks coming from the same import_france command
        self.assertEqual(len(counter), 1)
