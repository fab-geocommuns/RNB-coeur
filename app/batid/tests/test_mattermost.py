from unittest.mock import patch

from django.test import TestCase

from batid.services.mattermost import notify_if_error


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

    @patch("batid.services.mattermost.notify_tech")
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
