from unittest.mock import patch

from batid.tasks import backup_to_s3
from django.test import TestCase

SUCCESS_MSG = "Un nouveau backup de la base de production du RNB a été créé chez OVH : rnb_backup_test."


class TestS3Backups(TestCase):
    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.requests.post")
    def test_final_failure_notifies_once(
        self, post_mock, service_notify_mock, receiver_notify_mock
    ):
        """
        Input: the Scaleway backup creation API answers with a 500 error on both
        attempts of the task (max_retries=1), run through Celery with its retries.
        Expected: the task ends in FAILURE with the backup error, the service sends
        no notification and the generic failure receiver sends one single message
        naming the task and the error.
        """
        post_mock.return_value.status_code = 500

        result = backup_to_s3.apply()

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(str(result.result), "Error while creating the scaleway backup")
        self.assertEqual(post_mock.call_count, 2)
        service_notify_mock.assert_not_called()
        receiver_notify_mock.assert_called_once()
        msg = receiver_notify_mock.call_args.args[0]
        self.assertIn("batid.tasks.backup_to_s3", msg)
        self.assertIn("Error while creating the scaleway backup", msg)

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch("batid.services.s3_backup.backup_task.upload_to_s3")
    @patch("batid.services.s3_backup.backup_task.create_backup_download_url")
    @patch(
        "batid.services.s3_backup.backup_task.create_scaleway_db_backup",
        return_value=("backup-id", "rnb_backup_test"),
    )
    def test_success_notifies(
        self,
        create_mock,
        download_url_mock,
        upload_mock,
        remove_mock,
        service_notify_mock,
        receiver_notify_mock,
    ):
        """
        Input: every backup step succeeds on the first attempt.
        Expected: the task ends in SUCCESS, the service sends the success message
        once and the failure receiver sends nothing.
        """
        result = backup_to_s3.apply()

        self.assertEqual(result.state, "SUCCESS")
        service_notify_mock.assert_called_once_with(SUCCESS_MSG)
        receiver_notify_mock.assert_not_called()

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch("batid.services.s3_backup.backup_task.upload_to_s3")
    @patch("batid.services.s3_backup.backup_task.create_backup_download_url")
    @patch(
        "batid.services.s3_backup.backup_task.create_scaleway_db_backup",
        side_effect=[
            Exception("Error while creating the scaleway backup"),
            ("backup-id", "rnb_backup_test"),
        ],
    )
    def test_success_after_retry_notifies_success_only(
        self,
        create_mock,
        download_url_mock,
        upload_mock,
        remove_mock,
        service_notify_mock,
        receiver_notify_mock,
    ):
        """
        Input: the backup creation fails on the first attempt and every step
        succeeds on the retry.
        Expected: the task ends in SUCCESS after 2 attempts, the service sends the
        success message once and the failure receiver sends nothing.
        """
        result = backup_to_s3.apply()

        self.assertEqual(result.state, "SUCCESS")
        self.assertEqual(create_mock.call_count, 2)
        service_notify_mock.assert_called_once_with(SUCCESS_MSG)
        receiver_notify_mock.assert_not_called()
