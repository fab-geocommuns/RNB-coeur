from django.test import TestCase
from django.core.mail import EmailMultiAlternatives

from batid.services.email import build_reset_password_email


class ResetPasswordEmail(TestCase):
    def test(self):

        email = build_reset_password_email("token")

        self.assertIsInstance(email, EmailMultiAlternatives)
