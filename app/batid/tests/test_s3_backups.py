from django.test import TestCase
from batid.tasks import backup_to_s3
from unittest.mock import patch
import json


class TestS3Backups(TestCase):
    @patch("batid.services.s3_backup.backup_task.requests.post")
    @patch("celery.app.task.Task.request")
    def test_s3_backups_error_msg(self, task_id_mock, post_mock):
        # we simulate an error during the backup creation
        post_mock.return_value.status_code = 500
        task_id_mock.id = "some-task_id"

        # assert the exception message
        with self.assertRaises(Exception) as e:
            backup_to_s3()
            self.assertEqual(str(e.exception), "Error while creating the scaleway backup")
            
        
        # assert the mock was called twice (once for the backup creation and once for the mattermost notification)
        self.assertEqual(post_mock.call_count, 2)

        # get the data sent to mattermost
        data = json.loads(post_mock.call_args[1]["data"])
        self.assertEqual(data["username"], "backup-bot")
        self.assertEqual(data["text"], "Une erreur est survenue lors de la création d'un backup de la base de production du RNB : Error while creating the scaleway backup. Task ID : some-task_id")
        