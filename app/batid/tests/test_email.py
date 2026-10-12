from batid.services.email import (
    _reset_password_url,
    build_reset_password_email,
    make_unsubscribe_token,
    read_unsubscribe_token,
)
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
