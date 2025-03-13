from django.test import TestCase
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from batid.services.email import build_reset_password_email, _reset_password_url


class ResetPasswordEmail(TestCase):
    def test_email(self):

        email = build_reset_password_email("token", "email@address.com")

        self.assertIsInstance(email, EmailMultiAlternatives)

        # Check the email HTML content contains the link
        url = _reset_password_url("token")
        self.assertIn(url, email.alternatives[0][0])

    def test_reset_url(self):

        url = _reset_password_url("token")

        # Test this is a valid url
        validator = URLValidator()
        try:
            validator(url)
        except ValidationError:
            self.fail(f"{url} is not a valid URL")
