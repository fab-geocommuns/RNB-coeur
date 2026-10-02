from unittest.mock import patch

from batid.tasks import backup_to_s3
from django.test import TestCase


class TestS3Backups(TestCase):
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.requests.post")
    @patch("celery.app.task.Task.request")
    def test_s3_backups_error_msg(self, task_id_mock, post_mock, notify_tech_mock):
        """
        Input: the Scaleway backup creation API answers with a 500 error.
        Expected: the task raises, and a Tchap notification describing the error
        and the task id is sent.
        """
        post_mock.return_value.status_code = 500
        task_id_mock.id = "some-task_id"

        # assert the exception message
        with self.assertRaises(Exception) as e:
            backup_to_s3()
        self.assertEqual(str(e.exception), "Error while creating the scaleway backup")

        # only the backup creation call goes through requests.post
        self.assertEqual(post_mock.call_count, 1)

        notify_tech_mock.assert_called_once_with(
            "Une erreur est survenue lors de la création d'un backup de la base de production du RNB : Error while creating the scaleway backup. Task ID : some-task_id"
        )
