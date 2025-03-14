from unittest import mock

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from nanoid import generate
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog


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
    def test_full_process(self, mock_build_email):

        # ##################
        # PART 1: The user can login.

        data = {"username": "someone", "password": "1234"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 200)

        # ##################
        # PART 2: The user forgot its password. He makes a password request.

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

        # ##################
        # PART 3: The user is on the frontend and send the new password

        data = {"password": "new_password", "email": "someone@random.com"}

        # We need the token to rebuild the urlv
        user = User.objects.get(email="someone@random.com")
        token = default_token_generator.make_token(user)

        response = self.client.patch("/api/alpha/auth/change_password/" + token, data)

        self.assertEqual(response.status_code, 204)

        # Verify the new password is not logged via rest_framework_tracking
        # There must be only one log: the one when we touched /api/alpha/auth/reset_password/
        logs = APIRequestLog.objects.all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.first().path, "/api/alpha/auth/reset_password/")

        # ##################
        # PART 4: The user can login with the new password

        # The new password works
        data = {"username": "someone", "password": "new_password"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 200)

        # The old password does not work
        data = {"username": "someone", "password": "1234"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 400)

    def test_trigger_process_wrong_email(self):
        data = {"email": "no_in_db@nowhere.com"}
        response = self.client.post("/api/alpha/auth/reset_password/", data)

        # We still return 204 to avoid leaking information
        self.assertEqual(response.status_code, 204)

    def test_trigger_process_no_email(self):
        data = {}
        response = self.client.post("/api/alpha/auth/reset_password/", data)

        self.assertEqual(response.status_code, 400)

    def test_change_password_wrong_email(self):

        # Get the right token
        user = User.objects.get(email="someone@random.com")
        real_token = default_token_generator.make_token(user)

        # But send the wrong email
        data = {"password": "new_password", "email": "does_not_exist@random.com"}
        response = self.client.patch(
            "/api/alpha/auth/change_password/" + real_token, data
        )

        # We should receive a "fake" 204 to avoid leaking information
        self.assertEqual(response.status_code, 204)

        # But the password should not have changed
        data = {"username": "someone", "password": "1234"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 200)

    def test_change_password_wrong_token(self):

        # Get the wrong token
        fake_token = "fake_token"

        # But send the right email
        data = {"password": "new_password", "email": "someone@random.com"}
        response = self.client.patch(
            "/api/alpha/auth/change_password/" + fake_token, data
        )

        # We should receive a "fake" 204 to avoid leaking information
        self.assertEqual(response.status_code, 204)

        # But the password should not have changed
        data = {"username": "someone", "password": "1234"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 200)

    def test_choose_weak_password(self):

        # Get the token
        user = User.objects.get(email="someone@random.com")
        token = default_token_generator.make_token(user)

        data = {"password": "1111", "email": "someone@random.com"}

        response = self.client.patch("/api/alpha/auth/change_password/" + token, data)

        self.assertEqual(response.status_code, 400)


class ForgottenPasswordThrottling(APITestCase):
    def test_throttling(self):

        code_429 = 0
        code_204 = 0

        for _ in range(50):

            data = {
                "email": "someone@random.com",
                "password": "STRONG_zoeihfiuezhf77iuzgef$",
            }
            random_token = generate(size=10)

            response = self.client.patch(
                "/api/alpha/auth/change_password/" + random_token, data
            )

            if response.status_code == 429:
                code_429 += 1
            elif response.status_code == 204:
                code_204 += 1

        # We don't count precisely because the throttling because it includes request made in other tests
        self.assertTrue(code_429 > 0)
        self.assertTrue(code_204 > 0)
        self.assertTrue(code_429 + code_204 == 50)
        self.assertTrue(code_429 > code_204)
