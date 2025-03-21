from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.test import TestCase

from batid.services.email import _reset_password_url
from batid.services.email import build_reset_password_email


class ResetPasswordEmail(TestCase):
    def test_email(self):

        email = build_reset_password_email("token", "fake_bd64", "email@address.com")

        self.assertIsInstance(email, EmailMultiAlternatives)

        # Check the email HTML content contains the link
        url = _reset_password_url("fake_bd64", "token")
        self.assertIn(url, email.alternatives[0][0])

    def test_reset_url(self):

        url = _reset_password_url("fake_bd64", "token")

        # Test this is a valid url
        validator = URLValidator()
        try:
            validator(url)
        except ValidationError:
            self.fail(f"{url} is not a valid URL")
