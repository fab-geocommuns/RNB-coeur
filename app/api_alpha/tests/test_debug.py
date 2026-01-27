from unittest.mock import patch

from rest_framework.test import APITestCase


class DebugEndpointTest(APITestCase):
    @patch("batid.services.mattermost.notify_tech")
    def test_notify_if_error_is_called(self, mock_notify_tech):
        mock_notify_tech.return_value = None

        try:
            with self.assertRaises(Exception):
                self.client.get("/api/alpha/raise_exception")
        finally:
            pass

        # Verify notify_tech was called
        mock_notify_tech.assert_called_once()
