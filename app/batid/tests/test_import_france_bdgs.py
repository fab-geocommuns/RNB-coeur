from django.test import TestCase
from batid.management.commands.import_france_bdgs import create_tasks_list_france
from batid.management.commands.import_dpt_bdgs import steps_list


class ImportFranceTestCase(TestCase):
    def test_create_tasks_from_1(self):
        # create tasks when starting from the first dpt
        # There are 97 departements in France, excluding overseas territories
        tasks = create_tasks_list_france("01")
        self.assertEqual(len(tasks), 97 * len(steps_list()))

        tasks = create_tasks_list_france("")
        self.assertEqual(len(tasks), 97 * len(steps_list()))

    def test_create_tasks_from_custom(self):
        tasks = create_tasks_list_france("90")
        # expected tasks for 7 departements (90 to 96)

        self.assertEqual(len(tasks), 7 * len(steps_list()))
