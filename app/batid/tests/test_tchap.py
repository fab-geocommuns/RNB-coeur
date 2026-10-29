from unittest.mock import patch

from batid.services.tchap import notify_if_error, notify_tech
from batid.tasks import import_cities, import_plots
from django.test import TestCase, override_settings


class Decorator(TestCase):
    def test_function_without_error(self):
        """
        Test that the decorated function returns the correct output without error.
        """

        @notify_if_error
        def test_func():
            return "Success"

        result = test_func()
        self.assertEqual(result, "Success")

    @patch("batid.services.tchap.notify_tech")
    def test_function_with_error(self, notify):
        """
        Test that the decorator catches exceptions, sends a notification, and re-raises the exception.
        """

        @notify_if_error
        def test_func():
            raise Exception("Forced error")

        with self.assertRaises(Exception) as context:
            test_func()

        self.assertTrue("Forced error" in str(context.exception))

        notify.assert_called_once_with("Échec de test_func : Forced error")


class NotifyTaskFailure(TestCase):
    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_plots_job", side_effect=Exception("boom"))
    def test_final_failure_notifies_once(self, job, notify):
        """
        Input: import_plots (max_retries=3) raises on every attempt, run through
        Celery with its retries.
        Expected: 4 attempts, the task ends in FAILURE and one single French
        notification is sent, naming the task and the error.
        """
        result = import_plots.apply(args=["75", "2026-01-01"])

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(job.call_count, 4)
        notify.assert_called_once()
        msg = notify.call_args.args[0]
        self.assertTrue(msg.startswith("Échec de la tâche batid.tasks.import_plots ("))
        self.assertTrue(msg.endswith(") : boom"))

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_plots_job", side_effect=[Exception("boom"), None])
    def test_success_after_retry_does_not_notify(self, job, notify):
        """
        Input: import_plots fails on its first attempt and succeeds on the retry.
        Expected: the task ends in SUCCESS and no notification is sent.
        """
        result = import_plots.apply(args=["75", "2026-01-01"])

        self.assertEqual(result.state, "SUCCESS")
        notify.assert_not_called()

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_cities", side_effect=Exception("boom"))
    def test_any_task_notifies(self, job, notify):
        """
        Input: import_cities, a task that never carried a notification decorator,
        fails for good.
        Expected: the task ends in FAILURE and one notification is sent.
        """
        result = import_cities.apply(args=["75"])

        self.assertEqual(result.state, "FAILURE")
        notify.assert_called_once()

    @patch("batid.services.tchap.notify_tech", side_effect=Exception("tchap down"))
    @patch("batid.tasks.import_etalab_plots_job", side_effect=Exception("boom"))
    def test_tchap_down_does_not_change_task_state(self, job, notify):
        """
        Input: import_plots fails for good and sending the notification raises.
        Expected: the task still ends in FAILURE with its own error, the notification
        was attempted once and Celery logs the receiver error.
        """
        with self.assertLogs("celery.utils.dispatch.signal", level="ERROR") as logs:
            result = import_plots.apply(args=["75", "2026-01-01"])

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(str(result.result), "boom")
        notify.assert_called_once()
        self.assertEqual(len(logs.records), 1)

    def test_delay_on_former_decorated_task(self):
        """
        Input: .delay on import_plots, a task that used to carry @notify_if_error
        above @shared_task.
        Expected: the call is sent to Celery through apply_async with the task
        arguments.
        """
        with patch.object(import_plots, "apply_async") as apply_async:
            import_plots.delay("75", "2026-01-01")

        apply_async.assert_called_once_with(("75", "2026-01-01"), {})


class NotifyTech(TestCase):
    @override_settings(TCHAP_NOTIFICATIONS=False)
    @patch("batid.services.tchap.requests.put")
    def test_inactive_notifications(self, put_mock):
        """
        Input: notifications are disabled in settings.
        Expected: no HTTP request is made.
        """
        notify_tech("hello")
        put_mock.assert_not_called()

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr/",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_message_is_sent_to_the_room(self, put_mock):
        """
        Input: notifications are enabled and the Tchap env vars are set.
        Expected: one PUT on the Matrix send endpoint of the room, with the bearer
        token and a m.text body, using a unique transaction id.
        """
        put_mock.return_value.status_code = 200

        notify_tech("hello")
        notify_tech("hello")

        self.assertEqual(put_mock.call_count, 2)
        first, second = put_mock.call_args_list

        url = first.args[0]
        self.assertTrue(
            url.startswith(
                "https://matrix.example.gouv.fr/_matrix/client/v3/rooms/%21room%3Aexample.gouv.fr/send/m.room.message/"
            )
        )
        self.assertNotEqual(url, second.args[0])
        self.assertEqual(first.kwargs["json"], {"msgtype": "m.text", "body": "hello"})
        self.assertEqual(
            first.kwargs["headers"], {"Authorization": "Bearer syt_secret"}
        )

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_matrix_error_raises(self, put_mock):
        """
        Input: the Matrix API answers with a 401 (e.g. revoked token).
        Expected: an exception is raised, mentioning the status code.
        """
        put_mock.return_value.status_code = 401
        put_mock.return_value.text = '{"errcode":"M_UNKNOWN_TOKEN"}'

        with self.assertRaises(Exception) as context:
            notify_tech("hello")
        self.assertIn("401", str(context.exception))
        self.assertIn("M_UNKNOWN_TOKEN", str(context.exception))

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {"TCHAP_HOMESERVER_URL": "", "TCHAP_ACCESS_TOKEN": "", "TCHAP_ROOM_ID": ""},
    )
    @patch("batid.services.tchap.requests.put")
    def test_missing_configuration_raises(self, put_mock):
        """
        Input: notifications are enabled but the Tchap env vars are empty.
        Expected: an explicit exception, no HTTP request.
        """
        with self.assertRaises(Exception) as context:
            notify_tech("hello")
        self.assertIn("TCHAP_", str(context.exception))
        put_mock.assert_not_called()
