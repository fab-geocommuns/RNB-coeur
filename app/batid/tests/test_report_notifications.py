from unittest.mock import patch

import requests
from batid.models import Building, EmailNotificationOptOut, Report
from batid.services.brevo import BrevoTemplate
from batid.services.email import read_unsubscribe_token
from batid.services.reports.notifications import notify_report_author
from batid.tasks import send_report_activity_notification
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings

SEND_PATH = "batid.services.reports.notifications.send_transactional_email"


@override_settings(FRONTEND_URL="https://rnb.beta.gouv.fr")
@patch(SEND_PATH)
class NotifyReportAuthorTest(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="author", email="author@example.com"
        )
        self.actor = User.objects.create_user(
            username="actor", email="actor@example.com"
        )
        self.building = Building.objects.create(
            rnb_id="TEST00000001",
            point=Point(2.3522, 48.8566, srid=4326),
            shape="POLYGON((2.3522 48.8566, 2.3523 48.8566, 2.3523 48.8567, 2.3522 48.8567, 2.3522 48.8566))",
            status="constructed",
            is_active=True,
        )

    def _report(self, user=None, email=None):
        return Report.create(
            point=self.building.point,
            building=self.building,
            text="Initial report",
            email=email,
            user=user,
            tags=[],
        )

    def _notify(self, report, action, actor):
        message = report.messages.create(text="Reply text", created_by_user=actor)
        notify_report_author(
            report_id=report.id,
            action=action,
            actor_user_id=actor.id,
            message_id=message.id,
        )

    def test_sends_for_each_action(self, mock_send):
        """
        Input: report by an account author, an actor (different user) replies with
               fix/reject/comment.
        Expected: one Brevo email per action, to the author, with the
                  action-specific subject and label.
        """
        cases = {
            "fix": ("Votre signalement RNB a été traité", "résolu"),
            "reject": ("Votre signalement RNB a été refusé", "refusé"),
            "comment": ("Nouveau message sur votre signalement RNB", "commenté"),
        }
        for action, (subject, label) in cases.items():
            mock_send.reset_mock()
            self._notify(self._report(user=self.author), action, self.actor)
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            self.assertEqual(kwargs["template"], BrevoTemplate.REPORT_ACTIVITY)
            self.assertEqual(kwargs["to"], "author@example.com")
            self.assertEqual(kwargs["params"]["SUBJECT"], subject)
            self.assertEqual(kwargs["params"]["ACTIVITY_LABEL"], label)

    def test_params_hold_message_map_link_and_unsubscribe_link(self, mock_send):
        """
        Input: report on a building, an actor replies "fix" with "Reply text".
        Expected: params hold the message text, the map link (report= and q=rnb_id)
                  and an unsubscribe link whose token decodes to the recipient.
        """
        report = self._report(user=self.author)
        self._notify(report, "fix", self.actor)
        params = mock_send.call_args.kwargs["params"]
        self.assertEqual(params["MESSAGE_TEXT"], "Reply text")
        self.assertEqual(
            params["REPORT_URL"],
            f"https://rnb.beta.gouv.fr/carte?report={report.id}"
            f"&extra_layers=reports&q={self.building.rnb_id}",
        )
        prefix = "https://rnb.beta.gouv.fr/notifications/desinscription?token="
        self.assertTrue(params["UNSUBSCRIBE_URL"].startswith(prefix))
        token = params["UNSUBSCRIBE_URL"][len(prefix) :]
        self.assertEqual(read_unsubscribe_token(token), "author@example.com")

    def test_map_link_omits_q_without_building(self, mock_send):
        """
        Input: report whose building is None, an actor comments.
        Expected: the map link has report= but no q= parameter.
        """
        report = self._report(user=self.author)
        report.building = None
        report.save()
        self._notify(report, "comment", self.actor)
        report_url = mock_send.call_args.kwargs["params"]["REPORT_URL"]
        self.assertIn(f"report={report.id}", report_url)
        self.assertNotIn("&q=", report_url)

    def test_skip_when_no_email(self, mock_send):
        """
        Input: anonymous report with neither created_by_user nor created_by_email.
        Expected: no email is sent.
        """
        self._notify(self._report(), "comment", self.actor)
        mock_send.assert_not_called()

    def test_skip_when_actor_is_author_account(self, mock_send):
        """
        Input: account author replies to their own report.
        Expected: no email (one does not notify oneself).
        """
        self._notify(self._report(user=self.author), "comment", self.author)
        mock_send.assert_not_called()

    def test_skip_when_opted_out(self, mock_send):
        """
        Input: report author's email is in EmailNotificationOptOut.
        Expected: no email is sent.
        """
        EmailNotificationOptOut.opt_out("author@example.com")
        self._notify(self._report(user=self.author), "fix", self.actor)
        mock_send.assert_not_called()

    def test_skip_when_report_is_anonymous(self, mock_send):
        """
        Input: anonymous report with an unverified created_by_email, an account
               actor replies.
        Expected: no email, otherwise anyone could make RNB send their reply
                  text to any address typed on an anonymous report.
        """
        self._notify(self._report(email="victim@example.com"), "comment", self.actor)
        mock_send.assert_not_called()


@patch("batid.services.reports.notifications.notify_report_author")
class SendReportActivityNotificationRetryTest(TestCase):
    TASK_KWARGS = {"report_id": 1, "action": "fix", "actor_user_id": 1, "message_id": 1}

    def test_retries_when_brevo_cannot_be_reached(self, mock_notify):
        """
        Input: the notification keeps raising requests.ConnectionError, task run eagerly.
        Expected: 4 attempts (1 try + 3 retries), then the task ends failed.
        """
        mock_notify.side_effect = requests.ConnectionError("Brevo unreachable")
        result = send_report_activity_notification.apply(kwargs=self.TASK_KWARGS)
        self.assertEqual(mock_notify.call_count, 4)
        self.assertTrue(result.failed())

    def test_no_retry_after_read_timeout(self, mock_notify):
        """
        Input: the notification raises requests.ReadTimeout (Brevo may have sent it).
        Expected: a single attempt, so the author never gets the email twice.
        """
        mock_notify.side_effect = requests.ReadTimeout("Brevo too slow")
        result = send_report_activity_notification.apply(kwargs=self.TASK_KWARGS)
        self.assertEqual(mock_notify.call_count, 1)
        self.assertTrue(result.failed())
