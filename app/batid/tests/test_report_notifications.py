from batid.models import Building, EmailNotificationOptOut, Report
from batid.services.reports.notifications import notify_report_author
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core import mail
from django.test import TestCase, override_settings


@override_settings(
    FRONTEND_URL="https://rnb.beta.gouv.fr",
    RNB_SEND_ADDRESS="coucou@rnb.beta.gouv.fr",
    RNB_SEND_NAME="RNB",
    RNB_REPLY_TO_ADDRESS="reply@rnb.beta.gouv.fr",
)
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

    def _add_message(self, report, user=None, email=None):
        return report.messages.create(
            text="Reply text", created_by_user=user, created_by_email=email
        )

    def test_sends_for_each_action(self):
        """
        Input: report by an account author, an actor (different user) replies with
               fix/reject/comment.
        Expected: one email is sent to the author for every action.
        """
        for action in ["fix", "reject", "comment"]:
            mail.outbox = []
            report = self._report(user=self.author)
            message = self._add_message(report, user=self.actor)
            notify_report_author(report.id, action, self.actor.id, None, message.id)
            self.assertEqual(len(mail.outbox), 1, action)
            self.assertEqual(mail.outbox[0].to, ["author@example.com"])

    def test_skip_when_no_email(self):
        """
        Input: report with neither created_by_user nor created_by_email.
        Expected: no email is sent.
        """
        report = self._report(user=None, email=None)
        message = self._add_message(report, user=self.actor)
        notify_report_author(report.id, "comment", self.actor.id, None, message.id)
        self.assertEqual(len(mail.outbox), 0)

    def test_skip_when_actor_is_author_account(self):
        """
        Input: account author replies to their own report (actor_user_id == author).
        Expected: no email (one does not notify oneself).
        """
        report = self._report(user=self.author)
        message = self._add_message(report, user=self.author)
        notify_report_author(report.id, "comment", self.author.id, None, message.id)
        self.assertEqual(len(mail.outbox), 0)

    def test_skip_when_actor_is_author_email_case_insensitive(self):
        """
        Input: anonymous author "anon@example.com" replies with actor_email
               "ANON@Example.com" (different case).
        Expected: no email (author == actor, case ignored).
        """
        report = self._report(email="anon@example.com")
        message = self._add_message(report, email="ANON@Example.com")
        notify_report_author(report.id, "comment", None, "ANON@Example.com", message.id)
        self.assertEqual(len(mail.outbox), 0)

    def test_skip_when_opted_out(self):
        """
        Input: report author's email is in EmailNotificationOptOut.
        Expected: no email is sent.
        """
        EmailNotificationOptOut.opt_out("author@example.com")
        report = self._report(user=self.author)
        message = self._add_message(report, user=self.actor)
        notify_report_author(report.id, "fix", self.actor.id, None, message.id)
        self.assertEqual(len(mail.outbox), 0)

    def test_recipient_is_account_email(self):
        """
        Input: report by an account author, anonymous actor replies.
        Expected: email goes to the author account email.
        """
        report = self._report(user=self.author)
        message = self._add_message(report, email="someone@example.com")
        notify_report_author(report.id, "fix", None, "someone@example.com", message.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["author@example.com"])

    def test_recipient_is_anonymous_email(self):
        """
        Input: anonymous report (created_by_email), an account actor replies.
        Expected: email goes to the anonymous author's email.
        """
        report = self._report(email="anon@example.com")
        message = self._add_message(report, user=self.actor)
        notify_report_author(report.id, "fix", self.actor.id, None, message.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["anon@example.com"])
