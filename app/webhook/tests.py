from django.test import TestCase
from unittest.mock import Mock, patch
import os

# test the webhook view
class WebhookTestCase(TestCase):
    def setUp(self):
        self.env = patch.dict(
            "os.environ", {"SCALEWAY_WEBHOOK_TOKEN": "secret_token_xyz", "MATTERMOST_RNB_TECH_WEBHOOK_URL": "https://mattermost.example.com"}
        )

    @patch("webhook.views.requests")
    def test_webhook_200(self, mock_requests):
        with self.env:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"ok"
            mock_requests.post.return_value = mock_response
            
            invoice_start_date = "01-01-2024"
            threshold = 75

            response = self.client.post("/webhook/scaleway/secret_token_xyz", {"invoice_start_date": invoice_start_date, "threshold": threshold})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"ok")

            mock_requests.post.assert_called_once_with(
                os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL"),
                json={"text": f"Pour la période commençant le {invoice_start_date}, le seuil de consommation de {threshold}% du budget est dépassé."},
            )
    def test_webhook_401(self):
        with self.env:
            response = self.client.post("/webhook/scaleway/invalid_secret_token")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.content, b"Invalid token")
    
    def test_webhook_400(self):
        with self.env:
            response = self.client.post("/webhook/scaleway/secret_token_xyz", {"key": "value"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b"Bad Request")

    def test_missing_env_var(self):
        with self.env:
            del os.environ["MATTERMOST_RNB_TECH_WEBHOOK_URL"]
            
            invoice_start_date = "01-01-2024"
            treshold = "75"
            response = self.client.post("/webhook/scaleway/secret_token_xyz", {"invoice_start_date": invoice_start_date, "threshold": treshold})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b"Bad Request")