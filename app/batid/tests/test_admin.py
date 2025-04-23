from django.contrib.auth.models import User
from django.test import TestCase


class UserCreationForm(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="foobar", email="foo@bar.com", password="barbaz"
        )
        self.client.force_login(user=self.user)

    def test_has_email_field(self):
        response = self.client.get("/admin/auth/user/add/")
        self.assertContains(response, "email")
