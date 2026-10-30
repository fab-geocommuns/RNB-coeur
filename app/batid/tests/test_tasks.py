import json
import os
import tempfile
import time
import unittest
from unittest import mock

from batid.services.source import delete_files_older_than
from batid.tasks import create_sandbox_user
from django.test import SimpleTestCase, TestCase

from app.celery import app as celery_app


class TestCreateSandboxUserTask(TestCase):
    @mock.patch("batid.tasks.make_random_password")
    @mock.patch("requests.request")
    def test_create_sandbox_user_task(self, mock_request, mock_make_password):
        with self.settings(
            SANDBOX_URL="https://sandbox.example.test",
        ):
            user_data = {
                "last_name": "B",
                "first_name": "Julie",
                "email": "julie.b@exemple.com",
                "username": "juju",
                "organization_name": "Mairie d'Angoulème",
                "job_title": "responsable SIG",
            }

            mock_make_password.return_value = "randomly_generated_password"
            mock_request.return_value = mock.Mock(status_code=200)

            create_sandbox_user(user_data)

            mock_make_password.assert_called_once_with(length=24)

            call_args = mock_request.call_args
            self.assertEqual(call_args[0][0], "POST")
            self.assertEqual(
                call_args[0][1], "https://sandbox.example.test/api/alpha/auth/users/"
            )
            expected_json_params = {
                **user_data,
                "password": "randomly_generated_password",
            }
            self.assertEqual(
                json.dumps(call_args[1]["json"]), json.dumps(expected_json_params)
            )


class TestAcksLateTasks(SimpleTestCase):
    def test_acks_late_tasks(self):
        """
        Input: every Celery task registered under batid.tasks.
        Expected: the tasks with acks_late=True are exactly the 12 import tasks of #1144;
        sending tasks and update_all_cities_ban_ids_reliability stay acked on start.
        """
        acks_late_tasks = {
            name
            for name, task in celery_app.tasks.items()
            if name.startswith("batid.tasks.") and task.acks_late
        }
        self.assertSetEqual(
            acks_late_tasks,
            {
                f"batid.tasks.{name}"
                for name in [
                    "dl_source",
                    "convert_bdtopo",
                    "import_plots",
                    "import_ban",
                    "import_cities",
                    "inspect_candidates",
                    "flag_addresses_from_ban",
                    "compare_addresses_with_ban",
                    "create_dpt_bal_rnb_links",
                    "geocode_obsolete_addresses_task",
                    "update_addresses_from_ban_comparison_task",
                    "replace_obsolete_addresses_from_geocoding_task",
                ]
            },
        )


class TestDeleteFilesOlderThan(SimpleTestCase):
    SEVEN_DAYS = 7 * 24 * 3600

    def test_deletes_old_files_and_empty_dirs(self):
        """
        Input: root with a.csv and sub/b.csv, cutoff one minute in the future.
        Expected: returns 2, both files and sub/ deleted, root kept.
        """
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, "sub"))
            for path in ["a.csv", os.path.join("sub", "b.csv")]:
                open(os.path.join(root, path), "w").close()

            deleted = delete_files_older_than(root_dir=root, cutoff=time.time() + 60)

            self.assertEqual(deleted, 2)
            self.assertEqual(os.listdir(root), [])

    def test_keeps_extracted_file_with_old_mtime(self):
        """
        Input: sub/extracted.gpkg with an mtime 30 days ago (as an archive extraction
        sets it) but a fresh ctime, cutoff 7 days ago.
        Expected: returns 0, the file and sub/ kept.
        """
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, "sub"))
            file_path = os.path.join(root, "sub", "extracted.gpkg")
            open(file_path, "w").close()
            old_time = time.time() - 30 * 24 * 3600
            os.utime(file_path, (old_time, old_time))

            deleted = delete_files_older_than(
                root_dir=root, cutoff=time.time() - self.SEVEN_DAYS
            )

            self.assertEqual(deleted, 0)
            self.assertTrue(os.path.exists(file_path))

    def test_keeps_recent_empty_dir(self):
        """
        Input: root with an empty sub/ just created, cutoff 7 days ago.
        Expected: returns 0, sub/ kept (a running extraction may have just created it).
        """
        with tempfile.TemporaryDirectory() as root:
            sub_path = os.path.join(root, "sub")
            os.mkdir(sub_path)

            deleted = delete_files_older_than(
                root_dir=root, cutoff=time.time() - self.SEVEN_DAYS
            )

            self.assertEqual(deleted, 0)
            self.assertTrue(os.path.isdir(sub_path))

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_raises_on_unreadable_dir(self):
        """
        Input: root with locked/ (mode 000) containing a file, cutoff one minute in
        the future.
        Expected: PermissionError raised instead of a silent success.
        """
        with tempfile.TemporaryDirectory() as root:
            locked_path = os.path.join(root, "locked")
            os.mkdir(locked_path)
            open(os.path.join(locked_path, "a.csv"), "w").close()
            os.chmod(locked_path, 0)
            try:
                with self.assertRaises(PermissionError):
                    delete_files_older_than(root_dir=root, cutoff=time.time() + 60)
            finally:
                os.chmod(locked_path, 0o700)
