from unittest.mock import patch

from batid.services.tchap import notify_if_error, notify_tech
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

        notify.assert_called_once_with("Error while executing test_func: Forced error")


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
