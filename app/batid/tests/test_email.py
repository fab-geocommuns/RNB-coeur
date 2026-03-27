from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.template import Context
from django.template import Template
from django.test import override_settings
from django.test import TestCase

from batid.services.email import _reset_password_url
from batid.services.email import build_monthly_leaderboard_email
from batid.services.email import build_reset_password_email


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
        self.assertEqual(result, "https://rnb.beta.gouv.fr/static/batid/email/rnb-logo.png")


class MonthlyLeaderboardEmailLayoutTest(TestCase):
    @override_settings(
        URL="https://rnb.beta.gouv.fr",
        STATIC_URL="/static/",
        RNB_SEND_ADDRESS="coucou@rnb.beta.gouv.fr",
        RNB_REPLY_TO_ADDRESS="reply@rnb.beta.gouv.fr",
    )
    def test_email_uses_base_layout(self):
        """
        Input: year=2026, month=2
        Expected: HTML email contains the base layout markers (background color, logo img tag, contact footer)
        """
        email = build_monthly_leaderboard_email(2026, 2)
        html = email.alternatives[0][0]
        self.assertIn("#f5f5fe", html)
        self.assertIn("rnb-logo.png", html)
        self.assertIn("rnb@beta.gouv.fr", html)
        self.assertIn("février 2026", html)
