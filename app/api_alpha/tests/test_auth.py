import base64
from unittest import mock

from api_alpha.utils.sandbox_client import SandboxClientError
from batid.services.user import _b64_to_int, _int_to_b64, get_user_id_b64
from batid.tests.factories.users import ContributorUserFactory
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import override_settings
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
        self.email = "bill@bill.com"

    def setUp(self) -> None:
        u = User.objects.create_user(
            username=self.login, email=self.email, password=self.password
        )
        t = Token.objects.create(user=u)
        self.token = t.key

    def test_correct_creds(self):
        data = {"username": self.login, "password": self.password}
        response = self.client.post("/api/alpha/login/", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], self.token)

    def test_correct_creds_with_email(self):
        # user wants to connect with his mail
        data = {"username": self.email, "password": self.password}
        response = self.client.post("/api/alpha/login/", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], self.token)

    def test_wrong_creds(self):
        data = {"username": "wrong", "password": "wrong"}
        response = self.client.post("/api/alpha/login/", data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["non_field_errors"][0],
            "Impossible de se connecter avec les informations d'identification fournies.",
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

        data = {"password": "new_password", "confirm_password": "new_password"}

        # We need the token to rebuild the url
        user = User.objects.get(email="someone@random.com")
        token = default_token_generator.make_token(user)
        user_id_b64 = get_user_id_b64(user)

        response = self.client.patch(
            f"/api/alpha/auth/change_password/{user_id_b64}/{token}", data
        )

        self.assertEqual(response.status_code, 204)

        # Verify the new password is not logged via rest_framework_tracking
        logs = APIRequestLog.objects.filter(
            path__startswith="/api/alpha/auth/change_password/"
        )

        self.assertEqual(len(logs), 0)

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

    def test_change_password_wrong_id(self):

        # Get the right token
        user = User.objects.get(email="someone@random.com")
        real_token = default_token_generator.make_token(user)

        # But send the wrong id (MDk4NzY1 does not exist)
        data = {"password": "new_password", "confirm_password": "new_password"}
        response = self.client.patch(
            f"/api/alpha/auth/change_password/MDk4NzY1/{real_token}", data
        )

        # The response should be a 404
        self.assertEqual(response.status_code, 404)
        # The response should be empty (we don't want to explain why it failed)
        self.assertEqual(response.content, b"")

        # But the password should not have changed
        data = {"username": "someone", "password": "1234"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 200)

    def test_change_password_wrong_token(self):

        # Get the wrong token
        fake_token = "fake_token"

        # But send the right user b64 user id
        user = User.objects.get(email="someone@random.com")
        user_id_b64 = get_user_id_b64(user)

        # But send the right user b64 user id
        data = {"password": "new_password", "confirm_password": "new_password"}
        response = self.client.patch(
            f"/api/alpha/auth/change_password/{user_id_b64}/{fake_token}", data
        )

        # The response should be a 404
        self.assertEqual(response.status_code, 404)
        # The response should be empty (we don't want to explain why it failed)
        self.assertEqual(response.content, b"")

        # But the password should not have changed
        data = {"username": "someone", "password": "1234"}
        response = self.client.post("/api/alpha/login/", data)

        self.assertEqual(response.status_code, 200)

    def test_choose_weak_password(self):

        # Get the token and the user id
        user = User.objects.get(email="someone@random.com")
        token = default_token_generator.make_token(user)
        user_id_b64 = get_user_id_b64(user)

        data = {"password": "1111", "confirm_password": "1111"}

        response = self.client.patch(
            f"/api/alpha/auth/change_password/{user_id_b64}/{token}", data
        )

        self.assertEqual(response.status_code, 400)

    def test_different_passwords(self):

        # Get the token and the user id
        user = User.objects.get(email="someone@random.com")
        token = default_token_generator.make_token(user)
        user_id_b64 = get_user_id_b64(user)

        data = {
            "password": "STRONG_ozuhef875$",
            "confirm_password": "STRONG_DIFFERENT_ozuhef875$",
        }

        response = self.client.patch(
            f"/api/alpha/auth/change_password/{user_id_b64}/{token}", data
        )

        self.assertEqual(response.status_code, 400)

    def test_malformed_b64_user_id(self):

        user = User.objects.get(email="someone@random.com")
        token = default_token_generator.make_token(user)
        malformed_user_id_b64 = "WRONG_ID"

        data = {
            "password": "STRONG_ozuhef875$",
            "confirm_password": "STRONG_ozuhef875$",
        }

        response = self.client.patch(
            f"/api/alpha/auth/change_password/{malformed_user_id_b64}/{token}", data
        )

        self.assertEqual(response.status_code, 404)

    def test_b64_utils(self):

        # User id to b64
        encoded_id = _int_to_b64(42)
        self.assertEqual(encoded_id, "NDI=")

        # B64 to user id
        decoded_id = _b64_to_int("NDI=")
        self.assertEqual(decoded_id, 42)


class ForgottenPasswordThrottling(APITestCase):
    def test_throttling(self):

        code_429 = 0
        code_404 = 0

        # The throttling counter use Django cache.
        # Other auth tests (above) request "/api/alpha/auth/change_password/" which count in the throttling
        # We have to reset the cache to avoid the throttling to be already full
        cache.clear()

        for _ in range(15):

            data = {
                "password": "STRONG_zoeihfiuezhf77iuzgef$",
                "confirm_password": "STRONG_zoeihfiuezhf77iuzgef$",
            }
            random_token = generate(size=10)

            wrong_user_id = _int_to_b64(42)

            response = self.client.patch(
                f"/api/alpha/auth/change_password/{wrong_user_id}/{random_token}", data
            )

            if response.status_code == 429:
                code_429 += 1
            elif response.status_code == 404:
                code_404 += 1

        self.assertEqual(code_429, 5)
        self.assertEqual(code_404, 10)


class GetCurrentUserTokensTest(APITestCase):
    def setUp(self):
        self.user = ContributorUserFactory(
            username="testuserwithtoken",
            password="testpassword",
            email="testuserwithtoken@example.test",
        )
        self.token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    @override_settings(HAS_SANDBOX="true")
    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.get_user_token")
    def test_get_user_token_with_sandbox_token(self, mock_get_user_token):
        mock_get_user_token.return_value = "sandbox_token"

        response = self.client.get(
            f"/api/alpha/auth/users/me/tokens",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["production_token"], self.token.key)
        self.assertEqual(response.data["sandbox_token"], "sandbox_token")

    @override_settings(HAS_SANDBOX="true")
    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.get_user_token")
    def test_get_user_token_without_sandbox_token(self, mock_get_user_token):
        mock_get_user_token.side_effect = SandboxClientError("test")

        response = self.client.get(
            f"/api/alpha/auth/users/me/tokens",
            HTTP_AUTHORIZATION="Token " + self.token.key,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["production_token"], self.token.key)
        self.assertEqual(response.data["sandbox_token"], None)


class GetUserTokenTest(APITestCase):
    def setUp(self):
        self.user = ContributorUserFactory(
            username="testuserwithtoken",
            password="testpassword",
            email="testuserwithtoken@example.test",
        )
        self.token = Token.objects.get(user=self.user)
        self.user_without_token = User.objects.create_user(
            username="testuserwithouttoken",
            password="testpassword",
            email="testuserwithouttoken@example.test",
        )

    def test_get_user_token_not_in_sandbox(self):
        with self.settings(ENVIRONMENT="production"):
            response = self.client.get(
                f"/api/alpha/auth/users/{base64.b64encode(self.user.email.encode('utf-8')).decode('utf-8')}/token"
            )
            self.assertEqual(response.status_code, 404)

    def test_get_user_token_in_sandbox_with_wrong_secret_token(self):
        with self.settings(
            ENVIRONMENT="sandbox",
        ):
            response = self.client.get(
                f"/api/alpha/auth/users/{base64.b64encode(self.user.email.encode('utf-8')).decode('utf-8')}/token",
                HTTP_AUTHORIZATION="Bearer ",
            )
            self.assertEqual(response.status_code, 401)

        with self.settings(
            ENVIRONMENT="sandbox",
            SANDBOX_SECRET_TOKEN="right_token",
        ):
            response = self.client.get(
                f"/api/alpha/auth/users/{base64.b64encode(self.user.email.encode('utf-8')).decode('utf-8')}/token",
                HTTP_AUTHORIZATION="Bearer wrong_token",
            )
            self.assertEqual(response.status_code, 401)

    def test_get_user_token_in_sandbox_with_right_secret_token(self):
        with self.settings(
            ENVIRONMENT="sandbox",
            SANDBOX_SECRET_TOKEN="right_token",
        ):
            response = self.client.get(
                f"/api/alpha/auth/users/{base64.b64encode(self.user.email.encode('utf-8')).decode('utf-8')}/token",
                HTTP_AUTHORIZATION="Bearer right_token",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["token"], self.token.key)

    def test_get_user_token_in_sandbox_with_right_secret_token_but_no_token(self):
        with self.settings(
            ENVIRONMENT="sandbox",
            SANDBOX_SECRET_TOKEN="right_token",
        ):
            response = self.client.get(
                f"/api/alpha/auth/users/{base64.b64encode(self.user_without_token.email.encode('utf-8')).decode('utf-8')}/token",
                HTTP_AUTHORIZATION="Bearer right_token",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["token"], None)


class UnmirroredSandboxAccountTest(APITestCase):
    """A production account that was never mirrored to the sandbox used to fail
    twice over: the sandbox answered 500 on a plain "no such user", and
    production swallowed the error whole. The sandbox now answers 404, and
    production reports the gap instead of hiding it.
    """

    def setUp(self):
        self.user = ContributorUserFactory(
            username="mirrored",
            password="testpassword",
            email="mirrored@example.test",
        )
        self.token = Token.objects.get(user=self.user)

    def _sandbox_token_url(self, email):
        encoded = base64.b64encode(email.encode("utf-8")).decode("utf-8")
        return f"/api/alpha/auth/users/{encoded}/token"

    def test_sandbox_answers_404_for_an_unknown_user(self):
        """Asking the sandbox for the token of a user it does not have returns
        404, not a 500 from an unhandled DoesNotExist."""
        with self.settings(ENVIRONMENT="sandbox", SANDBOX_SECRET_TOKEN="right_token"):
            response = self.client.get(
                self._sandbox_token_url("never-mirrored@example.test"),
                HTTP_AUTHORIZATION="Bearer right_token",
            )
            self.assertEqual(response.status_code, 404)

    @override_settings(HAS_SANDBOX="true")
    @mock.patch("api_alpha.views.sentry_sdk.capture_message")
    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.get_user_token")
    def test_missing_sandbox_account_is_reported(self, mock_get_token, mock_capture):
        """A 404 from the sandbox means the account was never mirrored: the user
        still gets their production token, and the gap is reported to Sentry."""
        mock_get_token.side_effect = SandboxClientError(
            "not found", status_code=404, body=""
        )
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        response = self.client.get("/api/alpha/auth/users/me/tokens")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["production_token"], self.token.key)
        self.assertEqual(response.data["sandbox_token"], None)
        mock_capture.assert_called_once()
        self.assertEqual(mock_capture.call_args.kwargs["level"], "warning")

    @override_settings(HAS_SANDBOX="true")
    @mock.patch("api_alpha.views.sentry_sdk.capture_exception")
    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.get_user_token")
    def test_transport_error_is_reported_as_an_exception(
        self, mock_get_token, mock_capture
    ):
        """Any other sandbox failure is a genuine error and is captured as such,
        so it is not confused with a mirroring gap."""
        error = SandboxClientError("boom", status_code=500, body="server error")
        mock_get_token.side_effect = error
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        response = self.client.get("/api/alpha/auth/users/me/tokens")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sandbox_token"], None)
        mock_capture.assert_called_once_with(error)

    @override_settings(HAS_SANDBOX="true")
    @mock.patch("api_alpha.views.sentry_sdk.capture_message")
    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.get_user_token")
    def test_nothing_is_reported_when_the_sandbox_answers(
        self, mock_get_token, mock_capture
    ):
        """The normal case stays quiet."""
        mock_get_token.return_value = "sandbox_token"
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        response = self.client.get("/api/alpha/auth/users/me/tokens")

        self.assertEqual(response.data["sandbox_token"], "sandbox_token")
        mock_capture.assert_not_called()
