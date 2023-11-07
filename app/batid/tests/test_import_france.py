from django.test import TestCase
from batid.management.commands.import_france import create_tasks_list_france, dpts_list


class ImportFranceTestCase(TestCase):
    def test_create_tasks_from_1_cities(self):
        # create tasks for cities import
        tasks = create_tasks_list_france("01", "95", "cities")
        self.assertEqual(len(tasks), len(dpts_list()))

        tasks = create_tasks_list_france("", "777", "cities")
        self.assertEqual(len(tasks), len(dpts_list()))

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
        self.assertEqual(len(tasks), len(dpts_list()) * 2)

        tasks = create_tasks_list_france("", "", "plots")
        self.assertEqual(len(tasks), len(dpts_list()) * 2)

    def test_create_tasks_from_1_bdnb(self):
        # create tasks for bdnb import
        # there are 3 tasks per departement : dl_source and import_addresses and import_bdgs
        tasks = create_tasks_list_france("01", "95", "bdnb")
        self.assertEqual(len(tasks), len(dpts_list()) * 3)
