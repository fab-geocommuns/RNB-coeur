from unittest import mock

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class ADSEnpointsNoAuthTest(APITestCase):
    def __init__(self, *args, **kwargs):
        # init parent class
        super().__init__(*args, **kwargs)

        self.login = "bill"
        self.password = "billIsTheGoat"
        self.token = None

    def setUp(self) -> None:
        u = User.objects.create_user(
            username=self.login, email="bill@bill.com", password=self.password
        )
        t = Token.objects.create(user=u)
        self.token = t.key

    def test_correct_creds(self):
        data = {"username": self.login, "password": self.password}
        response = self.client.post("/api/alpha/login/", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], self.token)

    def test_wrong_creds(self):
        data = {"username": "wrong", "password": "wrong"}
        response = self.client.post("/api/alpha/login/", data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["non_field_errors"][0],
            "Unable to log in with provided credentials.",
        )


class ForgottenPassword(APITestCase):
    def setUp(self):

        User.objects.create_user(
            username="someone", email="someone@random.com", password="1234"
        )

    @mock.patch("api_alpha.views.build_reset_password_email")
    def test_trigger_process(self, mock_build_email):

        # We will verify the email is well sent.
        # To do so, we have to mock the email locally
        # from the return value of build_reset_password_email() which is also mocked
        # explanation: https://chatgpt.com/share/67d4203c-b510-800b-8d82-c8ad07b2611c (start from the conversation end, the beginning is a mess)
        mock_email = mock.Mock()
        mock_build_email.return_value = mock_email

        data = {"email": "someone@random.com"}
        response = self.client.post("/api/alpha/auth/reset_password/", data)

        self.assertEqual(response.status_code, 204)

        # Check the email was built and sent
        mock_build_email.assert_called_once()
        mock_email.send.assert_called_once()

    def test_trigger_process_wrong_email(self):
        data = {"email": "no_in_db@nowhere.com"}
        response = self.client.post("/api/alpha/auth/reset_password/", data)

        # We still return 204 to avoid leaking information
        self.assertEqual(response.status_code, 204)

    def test_trigger_process_no_email(self):
        data = {}
        response = self.client.post("/api/alpha/auth/reset_password/", data)

        self.assertEqual(response.status_code, 400)
