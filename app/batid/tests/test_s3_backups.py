from unittest.mock import patch

from batid.services.s3_backup.backup_task import upload_to_s3
from batid.services.tchap import Code, TchapLevel
from batid.tasks import backup_to_s3
from django.test import TestCase

SUCCESS_KWARGS = {
    "level": TchapLevel.SUCCESS,
    "title": "Sauvegarde de la base de prod créée chez OVH",
    "details": [("Nom", Code("rnb_backup_test")), ("Taille", "72,35 Go")],
}
BACKUP_SIZE = 72_350_000_000


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
        no notification and the generic failure receiver sends one single message,
        with the task name as "Tâche" detail, carrying the error.
        """
        post_mock.return_value.status_code = 500

        result = backup_to_s3.apply()

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(str(result.result), "Error while creating the scaleway backup")
        self.assertEqual(post_mock.call_count, 2)
        service_notify_mock.assert_not_called()
        receiver_notify_mock.assert_called_once()
        kwargs = receiver_notify_mock.call_args.kwargs
        self.assertEqual(kwargs["details"][0], ("Tâche", "batid.tasks.backup_to_s3"))
        self.assertEqual(kwargs["error"], "Error while creating the scaleway backup")

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch(
        "batid.services.s3_backup.backup_task.upload_to_s3", return_value=BACKUP_SIZE
    )
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
        service_notify_mock.assert_called_once_with(**SUCCESS_KWARGS)
        receiver_notify_mock.assert_not_called()

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch(
        "batid.services.s3_backup.backup_task.upload_to_s3", return_value=BACKUP_SIZE
    )
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
        service_notify_mock.assert_called_once_with(**SUCCESS_KWARGS)
        receiver_notify_mock.assert_not_called()

    @patch(
        "batid.services.s3_backup.backup_task.notify_tech",
        side_effect=Exception("tchap down"),
    )
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch(
        "batid.services.s3_backup.backup_task.upload_to_s3", return_value=BACKUP_SIZE
    )
    @patch("batid.services.s3_backup.backup_task.create_backup_download_url")
    @patch(
        "batid.services.s3_backup.backup_task.create_scaleway_db_backup",
        return_value=("backup-id", "rnb_backup_test"),
    )
    def test_tchap_down_after_success_does_not_rerun_backup(
        self, create_mock, download_url_mock, upload_mock, remove_mock, notify_mock
    ):
        """
        Input: every backup step succeeds, then the Tchap success message raises.
        Expected: the task ends in SUCCESS after one single attempt, the backup is
        not started again and the error is logged.
        """
        with self.assertLogs(level="ERROR"):
            result = backup_to_s3.apply()

        self.assertEqual(result.state, "SUCCESS")
        create_mock.assert_called_once()
        notify_mock.assert_called_once()

    @patch("batid.services.s3_backup.backup_task.boto3.client")
    @patch("batid.services.s3_backup.backup_task.requests.get")
    def test_download_error_raises(self, get_mock, client_mock):
        """
        Input: the Scaleway backup download answers with a 403.
        Expected: upload_to_s3 raises an error naming the status, nothing is
        uploaded to the bucket.
        """
        get_mock.return_value.status_code = 403

        with self.assertRaises(Exception) as context:
            upload_to_s3("rnb_backup_test", "https://download.example")

        self.assertEqual(
            str(context.exception), "Error 403 while downloading the scaleway backup"
        )
        client_mock.return_value.upload_fileobj.assert_not_called()

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch("batid.services.s3_backup.backup_task.upload_to_s3", return_value=1000)
    @patch("batid.services.s3_backup.backup_task.create_backup_download_url")
    @patch(
        "batid.services.s3_backup.backup_task.create_scaleway_db_backup",
        return_value=("backup-id", "rnb_backup_test"),
    )
    def test_too_small_backup_fails(
        self,
        create_mock,
        download_url_mock,
        upload_mock,
        remove_mock,
        service_notify_mock,
        receiver_notify_mock,
    ):
        """
        Input: every backup step succeeds but the stored backup is 1 000 bytes, on
        both attempts of the task.
        Expected: the task ends in FAILURE, older backups are kept, no success
        message; one failure message naming the task and the size in its error.
        """
        result = backup_to_s3.apply()

        self.assertEqual(result.state, "FAILURE")
        remove_mock.assert_not_called()
        service_notify_mock.assert_not_called()
        error = "Backup rnb_backup_test is too small: 1000 bytes, minimum 50000000000"
        receiver_notify_mock.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.backup_to_s3"),
                ("Identifiant", result.id),
                ("Arguments", "aucun"),
            ],
            error=error,
        )

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.services.s3_backup.backup_task.notify_tech")
    @patch("batid.services.s3_backup.backup_task.remove_older_backups")
    @patch("batid.services.s3_backup.backup_task.requests.get")
    @patch("batid.services.s3_backup.backup_task.create_backup_download_url")
    @patch(
        "batid.services.s3_backup.backup_task.create_scaleway_db_backup",
        return_value=("backup-id", "rnb_backup_test"),
    )
    def test_download_error_fails_the_task(
        self,
        create_mock,
        download_url_mock,
        get_mock,
        remove_mock,
        service_notify_mock,
        receiver_notify_mock,
    ):
        """
        Input: the Scaleway backup download answers with a 403 on both attempts of
        the task, run with .apply(): Celery runs the retry eagerly, in the same call.
        Expected: 2 download attempts, the task ends in FAILURE, older backups are
        kept, no success message; one failure message naming the task, with the
        403 in its error.
        """
        get_mock.return_value.status_code = 403

        result = backup_to_s3.apply()

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(get_mock.call_count, 2)
        remove_mock.assert_not_called()
        service_notify_mock.assert_not_called()
        receiver_notify_mock.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.backup_to_s3"),
                ("Identifiant", result.id),
                ("Arguments", "aucun"),
            ],
            error="Error 403 while downloading the scaleway backup",
        )
