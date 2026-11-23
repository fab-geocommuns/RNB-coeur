from unittest.mock import MagicMock, patch

from batid.services.brevo import BrevoTemplate
from batid.services.mfa import MFAChange
from batid.tasks import send_mfa_change_notification
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

SEND_PATH = "batid.services.mfa.send_transactional_email"
CHANGED_AT = "2026-11-19T13:32:07+00:00"


@override_settings(FRONTEND_URL="https://rnb.beta.gouv.fr")
@patch(SEND_PATH)
class MFAChangeNotificationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="jdupont", email="jdupont@exemple.fr"
        )

    def notify(self, *, change=MFAChange.APP_REPLACED, changed_at=CHANGED_AT):
        send_mfa_change_notification(
            user_id=self.user.pk, change=change, changed_at=changed_at
        )

    def test_sends_one_email_per_change(self, mock_send):
        """
        Input: the task called with each change, as the plain strings Celery passes,
               changed at 13:32 UTC in winter.
        Expected: one Brevo email per change, to the owner, with the MFA template,
                  the change-specific subject and text, the username, the change
                  time in Paris time and the forgotten password link of the site.
        """
        cases = {
            "app_activated": (
                "Double authentification activée sur votre compte RNB",
                "La double authentification a été activée sur votre compte.",
            ),
            "app_replaced": (
                "Application d'authentification changée sur votre compte RNB",
                "L'application d'authentification de votre compte a été remplacée. "
                "Vos anciens codes de secours ne fonctionnent plus.",
            ),
            "backup_codes_regenerated": (
                "Codes de secours régénérés sur votre compte RNB",
                "De nouveaux codes de secours ont été générés pour votre compte. "
                "Les anciens ne fonctionnent plus.",
            ),
        }
        self.assertEqual(set(cases), {change.value for change in MFAChange})
        for change, (subject, text) in cases.items():
            mock_send.reset_mock()

            self.notify(change=change)

            mock_send.assert_called_once_with(
                template=BrevoTemplate.MFA_CHANGE,
                to="jdupont@exemple.fr",
                params={
                    "SUBJECT": subject,
                    "CHANGE_TEXT": text,
                    "ACCOUNT": "jdupont",
                    "CHANGED_AT": "19/11/2026 à 14 h 32 (heure de Paris)",
                    "PASSWORD_RESET_URL": "https://rnb.beta.gouv.fr/auth/mdp-oublie",
                },
            )

    def test_change_time_in_summer(self, mock_send):
        """
        Input: a change at 12:05 UTC on 1 July.
        Expected: "01/07/2026 à 14 h 05 (heure de Paris)", summer time applied.
        """
        self.notify(changed_at="2026-07-01T12:05:00+00:00")

        self.assertEqual(
            mock_send.call_args.kwargs["params"]["CHANGED_AT"],
            "01/07/2026 à 14 h 05 (heure de Paris)",
        )

    def test_skips_an_account_without_email(self, mock_send):
        """
        Input: an account with an empty email.
        Expected: no email sent, no error.
        """
        self.user.email = ""
        self.user.save()

        self.notify()

        mock_send.assert_not_called()


@override_settings(EMAIL_SENDING_ENABLED=True, BREVO_API_KEY="test-key")
@patch("batid.services.brevo.requests.post")
class MFAChangeNotificationRetryTest(TestCase):
    def test_retries_when_brevo_is_unavailable(self, mock_post):
        """
        Input: Brevo answers 503, then 201, task run eagerly.
        Expected: a second attempt sends the email and the task succeeds.
        """
        user = User.objects.create_user(username="jdupont", email="jdupont@exemple.fr")
        mock_post.side_effect = [
            MagicMock(ok=False, status_code=503, text=""),
            MagicMock(ok=True),
        ]

        result = send_mfa_change_notification.apply(
            kwargs={
                "user_id": user.pk,
                "change": "app_replaced",
                "changed_at": CHANGED_AT,
            }
        )

        self.assertEqual(mock_post.call_count, 2)
        self.assertTrue(result.successful())
