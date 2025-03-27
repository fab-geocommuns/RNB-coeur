from unittest import mock

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from nanoid import generate
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from batid.services.user import _b64_to_int
from batid.services.user import _int_to_b64
from batid.services.user import get_user_id_b64


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

        self.assertEqual(len(logs), 1)
        self.assertNotIn("new_password", logs.first().query_params)

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


class UserCreation(APITestCase):
    def test_create_user(self):
        data = {
            "last_name": "Y",
            "first_name": "Julie",
            "email": "julie.y@exemple.com",
            "username": "jujuyy",
            "password": "tajine",
            "organization_name": "Mairie d'Angoulème",
            "job_title": "responsable SIG",
        }
        response = self.client.post("/api/alpha/auth/user/create/", data)

        self.assertEqual(response.status_code, 201)

        julie = User.objects.prefetch_related("organizations", "profile").get(
            first_name="Julie"
        )
        self.assertEqual(julie.last_name, "Y")
        self.assertEqual(julie.email, "julie.y@exemple.com")
        # we check the password is properly hashed
        self.assertNotEqual(julie.password, "tajine")
        self.assertIsNotNone(julie.password)
        self.assertEqual(julie.username, "jujuyy")
        self.assertEqual(len(julie.organizations.all()), 1)
        orgas = julie.organizations.all()
        self.assertEqual(orgas[0].name, "Mairie d'Angoulème")
        self.assertEqual(julie.profile.job_title, "responsable SIG")

        # check for unicity constraints
        data = {
            "last_name": "Y",
            "first_name": "Julie",
            "email": "julie.y@exemple.com",
            "username": "jujuyy",
            "password": "tajine",
            "organization_name": "Mairie d'Angoulème",
            "job_title": "responsable SIG",
        }
        response = self.client.post("/api/alpha/auth/user/create/", data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "email": ["A user with this email address already exists"],
                "username": ["A user with that username already exists."],
            },
        )

    def test_create_user_no_orga(self):
        # come as you are: someone can create an account without having a job or an organization
        data = {
            "last_name": "Y",
            "first_name": "Julie",
            "email": "julie.y@exemple.com",
            "username": "jujuyy",
            "password": "tajine",
        }
        response = self.client.post("/api/alpha/auth/user/create/", data)

        self.assertEqual(response.status_code, 201)

    def test_mandatory_info(self):
        data = {}
        response = self.client.post("/api/alpha/auth/user/create/", data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "last_name": ["This field is required."],
                "first_name": ["This field is required."],
                "email": ["This field is required."],
                "username": ["This field is required."],
                "password": ["This field is required."],
            },
        )
