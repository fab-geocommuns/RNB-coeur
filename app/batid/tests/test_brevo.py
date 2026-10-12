from unittest.mock import MagicMock, patch

from batid.services.brevo import BrevoError, BrevoTemplate, send_transactional_email
from django.test import SimpleTestCase, override_settings


@override_settings(BREVO_API_KEY="test-key", RNB_REPLY_TO_ADDRESS="reply@rnb.fr")
@patch("batid.services.brevo.requests.post")
class SendTransactionalEmailTest(SimpleTestCase):
    def test_posts_template_recipient_and_params(self, mock_post):
        """
        Input: send REPORT_ACTIVITY to "a@b.fr" with params {"X": "1"}, Brevo answers 201.
        Expected: one POST to the Brevo SMTP API with the api key header, the template
                  id, the recipient, the reply-to, the params, and a timeout.
        """
        mock_post.return_value = MagicMock(ok=True)
        send_transactional_email(
            template=BrevoTemplate.REPORT_ACTIVITY, to="a@b.fr", params={"X": "1"}
        )
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(kwargs["headers"]["api-key"], "test-key")
        self.assertEqual(
            kwargs["json"],
            {
                "templateId": BrevoTemplate.REPORT_ACTIVITY.value,
                "to": [{"email": "a@b.fr"}],
                "replyTo": {"email": "reply@rnb.fr"},
                "params": {"X": "1"},
            },
        )
        self.assertEqual(kwargs["timeout"], 10)

    def test_raises_when_brevo_refuses(self, mock_post):
        """
        Input: Brevo answers 400 with an error body.
        Expected: BrevoError carrying the status and the body.
        """
        mock_post.return_value = MagicMock(
            ok=False, status_code=400, text='{"code":"invalid_parameter"}'
        )
        with self.assertRaisesRegex(BrevoError, "400.*invalid_parameter"):
            send_transactional_email(
                template=BrevoTemplate.REPORT_ACTIVITY, to="a@b.fr", params={}
            )
