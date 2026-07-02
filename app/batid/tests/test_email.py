from batid.models import Building, Report
from batid.services.email import (
    _reset_password_url,
    build_report_activity_email,
    build_reset_password_email,
    make_unsubscribe_token,
    read_unsubscribe_token,
)
from django.contrib.gis.geos import Point
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.template import Context, Template
from django.test import TestCase, override_settings


class ResetPasswordEmail(TestCase):
    @override_settings(
        RNB_SEND_ADDRESS="coucou@rnb.beta.gouv.fr",
        RNB_REPLY_TO_ADDRESS="reply@rnb.beta.gouv.fr",
    )
    def test_email(self):
        email = build_reset_password_email("token", "fake_bd64", "email@address.com")
        self.assertIsInstance(email, EmailMultiAlternatives)
        # Check the email HTML content contains the link
        url = _reset_password_url("fake_bd64", "token")
        self.assertIn(url, email.alternatives[0][0])

    @override_settings(FRONTEND_URL="http://rnb.beta.gouv.fr")
    def test_reset_url(self):
        url = _reset_password_url("fake_bd64", "token")
        # Test this is a valid url
        validator = URLValidator()
        try:
            validator(url)
        except ValidationError:
            self.fail(f"{url} is not a valid URL")


class UnsubscribeTokenTest(TestCase):
    def test_token_roundtrip(self):
        """
        Input: make_unsubscribe_token("User@Example.com") then read it back.
        Expected: read returns the lowercased email "user@example.com".
        """
        token = make_unsubscribe_token("User@Example.com")
        self.assertEqual(read_unsubscribe_token(token), "user@example.com")

    def test_tampered_token_raises(self):
        """
        Input: a valid token with its last character altered.
        Expected: read_unsubscribe_token raises signing.BadSignature.
        """
        token = make_unsubscribe_token("user@example.com")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with self.assertRaises(signing.BadSignature):
            read_unsubscribe_token(tampered)


@override_settings(
    FRONTEND_URL="https://rnb.beta.gouv.fr",
    RNB_SEND_ADDRESS="coucou@rnb.beta.gouv.fr",
    RNB_SEND_NAME="RNB",
    RNB_REPLY_TO_ADDRESS="reply@rnb.beta.gouv.fr",
)
class ReportActivityEmailTest(TestCase):
    def setUp(self):
        self.building = Building.objects.create(
            rnb_id="TEST00000001",
            point=Point(2.3522, 48.8566, srid=4326),
            shape="POLYGON((2.3522 48.8566, 2.3523 48.8566, 2.3523 48.8567, 2.3522 48.8567, 2.3522 48.8566))",
            status="constructed",
            is_active=True,
        )
        self.report = Report.create(
            point=self.building.point,
            building=self.building,
            text="Initial report",
            email="reporter@example.com",
            user=None,
            tags=[],
        )
        self.message = self.report.messages.create(
            text="C'est corrigé maintenant", created_by_email="actor@example.com"
        )

    def _html(self, email):
        return email.alternatives[0][0]

    def test_subject_per_action(self):
        """
        Input: build_report_activity_email for each action fix/reject/comment.
        Expected: subject matches the action-specific French wording.
        """
        cases = {
            "fix": "Votre signalement RNB a été traité",
            "reject": "Votre signalement RNB a été refusé",
            "comment": "Nouveau message sur votre signalement RNB",
        }
        for action, subject in cases.items():
            email = build_report_activity_email(
                self.report, action, self.message, "reporter@example.com"
            )
            self.assertEqual(email.subject, subject)

    def test_html_contains_message_map_and_unsubscribe(self):
        """
        Input: build_report_activity_email(report with building, "fix", message, recipient).
        Expected: HTML contains the message text, the map link (report= and q=rnb_id)
                  and an unsubscribe link whose token decodes to the recipient email.
        """
        email = build_report_activity_email(
            self.report, "fix", self.message, "reporter@example.com"
        )
        html = self._html(email)
        self.assertIn("C&#x27;est corrigé maintenant", html)
        self.assertIn(f"report={self.report.id}", html)
        self.assertIn(f"q={self.building.rnb_id}", html)
        self.assertIn("/notifications/desinscription?token=", html)
        token = html.split("token=")[1].split('"')[0]
        self.assertEqual(read_unsubscribe_token(token), "reporter@example.com")

    def test_map_link_omits_q_without_building(self):
        """
        Input: report whose building is None.
        Expected: map link has report= but no q= parameter.
        """
        self.report.building = None
        self.report.save()
        email = build_report_activity_email(
            self.report, "comment", self.message, "reporter@example.com"
        )
        html = self._html(email)
        self.assertIn(f"report={self.report.id}", html)
        self.assertNotIn("&q=", html)


class AbsoluteStaticTagTest(TestCase):
    @override_settings(URL="https://rnb.beta.gouv.fr", STATIC_URL="/static/")
    def test_absolute_static_returns_full_url(self):
        """
        Input: static path 'batid/email/rnb-logo.png', settings.URL='https://rnb.beta.gouv.fr', STATIC_URL='/static/'
        Expected: returns 'https://rnb.beta.gouv.fr/static/batid/email/rnb-logo.png'
        """
        t = Template(
            "{% load email_tags %}{% absolute_static 'batid/email/rnb-logo.png' %}"
        )
        result = t.render(Context({}))
        self.assertEqual(
            result, "https://rnb.beta.gouv.fr/static/batid/email/rnb-logo.png"
        )
