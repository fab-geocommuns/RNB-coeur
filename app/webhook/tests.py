from unittest.mock import patch

from batid.services.tchap import TchapLevel
from django.test import TestCase


# test the webhook view
class WebhookTestCase(TestCase):
    def setUp(self):
        self.env = patch.dict(
            "os.environ",
            {"SCALEWAY_WEBHOOK_TOKEN": "secret_token_xyz"},
        )

    @patch("webhook.views.notify_tech")
    def test_webhook_200(self, mock_notify_tech):
        """
        Input: a valid Scaleway budget alert with the right token.
        Expected: 200 response and one alert is sent to Tchap, with the threshold
        and the period start date as detail lines.
        """
        with self.env:
            invoice_start_date = "01-01-2024"
            threshold = 75

            response = self.client.post(
                "/webhook/scaleway/secret_token_xyz",
                data={"invoice_start_date": invoice_start_date, "threshold": threshold},
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"ok")

            mock_notify_tech.assert_called_once_with(
                level=TchapLevel.ALERT,
                title="Alerte budget Scaleway",
                details=[("Seuil", "75 %"), ("Période", "à partir du 01-01-2024")],
            )

    def test_webhook_401(self):
        """
        Input: a POST with an invalid secret token.
        Expected: 401 response, no notification sent.
        """
        with self.env:
            response = self.client.post("/webhook/scaleway/invalid_secret_token")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.content, b"Invalid token")

    @patch("webhook.views.notify_tech")
    def test_webhook_400(self, mock_notify_tech):
        """
        Input: a POST with the right token but without the expected fields.
        Expected: 400 response, no notification sent.
        """
        with self.env:
            response = self.client.post(
                "/webhook/scaleway/secret_token_xyz",
                {"key": "value"},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b"Bad Request")
            mock_notify_tech.assert_not_called()
