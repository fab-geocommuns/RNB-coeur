from collections import Counter
from datetime import date
from unittest import mock

from batid.management.commands.import_france import (
    create_tasks_list_france,
    dpt_list_metropole,
)
from django.test import TestCase


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

    @mock.patch(
        "batid.services.imports.import_plots.fetch_etalab_release_dates",
        return_value=[date(2026, 6, 1), date(2026, 9, 1)],
    )
    def test_create_tasks_from_1_plots(self, fetch_mock):
        """
        Input: plots import over all metropolitan departements, Etalab index
        mocked to list the 2026-06-01 and 2026-09-01 releases.
        Expected: the index is read once for the whole run, 2 tasks per
        departement (dl_source then import_plots), every task carrying
        "2026-09-01".
        """
        tasks = create_tasks_list_france("01", "95", "plots")
        fetch_mock.assert_called_once()
        self.assertEqual(len(tasks), len(dpt_list_metropole()) * 2)

        for dl_task, import_task in zip(tasks[::2], tasks[1::2]):
            dpt = import_task.args[0]
            self.assertEqual(dl_task.args, ("plot", {"dpt": dpt, "date": "2026-09-01"}))
            self.assertEqual(import_task.args, (dpt, "2026-09-01"))

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
