import base64
import re
from unittest import mock
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from nanoid import generate
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from api_alpha.permissions import RNBContributorPermission
from api_alpha.utils.sandbox_client import SandboxClientError
from batid.services.user import _b64_to_int
from batid.services.user import _int_to_b64
from batid.services.user import get_user_id_b64


class UserCreation(APITestCase):
    def setUp(self):
        Group.objects.get_or_create(name=settings.CONTRIBUTORS_GROUP_NAME)
        self.julie_data = {
            "last_name": "B",
            "first_name": "Julie",
            "email": "julie.b+test@exemple.com",
            "username": "juju",
            "password": "tajine",
            "organization_name": "Mairie d'Angoulème",
            "job_title": "responsable SIG",
        }
        self.override = self.settings(
            RNB_SEND_ADDRESS="coucou@rnb.beta.gouv.fr",
            FRONTEND_URL="https://rnb.beta.gouv.fr",
        )

        self.override.enable()

    def tearDown(self):
        self.override.disable()

    @mock.patch("api_alpha.views.validate_captcha")
    def test_create_user(self, mock_validate_captcha):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/alpha/auth/users/", self.julie_data)
        self.assertEqual(response.status_code, 201)
        julie = User.objects.prefetch_related("organizations", "profile").get(
            first_name="Julie"
        )
        self.assertEqual(julie.last_name, "B")
        self.assertEqual(julie.email, "julie.b+test@exemple.com")
        # we check the password is properly hashed
        self.assertNotEqual(julie.password, "tajine")
        self.assertIsNotNone(julie.password)
        self.assertEqual(julie.username, "juju")
        self.assertEqual(len(julie.organizations.all()), 1)
        orgas = julie.organizations.all()
        self.assertEqual(orgas[0].name, "Mairie d'Angoulème")
        self.assertEqual(julie.profile.job_title, "responsable SIG")
        # Julie is a contributor and has a token
        self.assertTrue(
            julie.groups.filter(name=settings.CONTRIBUTORS_GROUP_NAME).exists()
        )
        self.assertTrue(Token.objects.filter(user=julie).exists)

        # the user is not active yet
        self.assertFalse(julie.is_active)
        # activation email has been sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [julie.email])

        # check for unicity constraints
        response = self.client.post("/api/alpha/auth/users/", self.julie_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "email": ["Un utilisateur avec cette adresse email existe déjà."],
                "username": ["Un utilisateur avec ce nom existe déjà."],
            },
        )
        # check also that you cannot create a new user with a username being an existing email address
        new_data = self.julie_data.copy()
        new_data["username"] = self.julie_data["email"]
        new_data["email"] = "another_email@exemple.fr"
        response = self.client.post("/api/alpha/auth/users/", new_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "username": ["Un utilisateur avec ce nom existe déjà."],
            },
        )

        # check also that you cannot create a new user with an email being an existing username
        new_data = self.julie_data.copy()
        new_data["email"] = self.julie_data["username"]
        new_data["username"] = "another_username"
        response = self.client.post("/api/alpha/auth/users/", new_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "email": ["Un utilisateur avec cette adresse email existe déjà."],
            },
        )

    @mock.patch("api_alpha.views.validate_captcha")
    def test_create_user_no_orga(self, mock_validate_captcha):
        # come as you are: someone can create an account without having a job or an organization
        self.julie_data.pop("organization_name")
        response = self.client.post("/api/alpha/auth/users/", self.julie_data)
        self.assertEqual(response.status_code, 201)

    @mock.patch("api_alpha.views.validate_captcha")
    def test_mandatory_info(self, mock_validate_captcha):
        data = {}
        response = self.client.post("/api/alpha/auth/users/", data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "last_name": ["Ce champ est obligatoire."],
                "first_name": ["Ce champ est obligatoire."],
                "email": ["Ce champ est obligatoire."],
                "username": ["Ce champ est obligatoire."],
                "password": ["Ce champ est obligatoire."],
            },
        )

    @mock.patch("api_alpha.views.validate_captcha")
    def test_full_account_activation_scenario(self, mock_validate_captcha):
        # julie creates her account
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post("/api/alpha/auth/users/", self.julie_data)

        julie = User.objects.prefetch_related("organizations", "profile").get(
            first_name="Julie"
        )

        # the account is inactive
        self.assertFalse(julie.is_active)
        # but she has received an email
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [julie.email])
        self.assertTrue(
            email.alternatives, "error : email has no HTML version available"
        )

        html_content = email.alternatives[0][0]

        # the mail contains an activation link
        match = re.search(r'"([^"]+)"', html_content)
        self.assertIsNotNone(match, "No link found in email")
        activation_link = match.group(1)
        activation_link = urlparse(activation_link)
        activation_link = activation_link.path

        # Julie clicks on the link
        resp = self.client.get(activation_link)

        # She is redirected to the website where she will be notified of the activation success
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp["Location"],
            f"https://rnb.beta.gouv.fr/activation?status=success&email=julie.b%2Btest%40exemple.com",
        )

        # her account is now active!
        julie.refresh_from_db()
        self.assertTrue(julie.is_active)

    @mock.patch("api_alpha.views.validate_captcha")
    def test_dont_mess_with_activation_to(self, mock_validate_captcha):
        # julie creates her account
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post("/api/alpha/auth/users/", self.julie_data)

        julie = User.objects.prefetch_related("organizations", "profile").get(
            first_name="Julie"
        )

        # the account is inactive
        self.assertFalse(julie.is_active)
        # but she has received an email
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [julie.email])
        self.assertTrue(
            email.alternatives, "error : email has no HTML version available"
        )

        html_content = email.alternatives[0][0]

        # the mail contains an activation link
        match = re.search(r'"([^"]+)"', html_content)
        self.assertIsNotNone(match, "No link found in email")
        activation_link = match.group(1)
        activation_link = urlparse(activation_link)
        activation_link = activation_link.path

        # sneaky Julie modifies the token
        activation_link = activation_link[:-5]
        activation_link = activation_link + "xxxx/"

        # Julie clicks on the modified link
        resp = self.client.get(activation_link)

        # She is redirected to the website where she will be notified of the activation error
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp["Location"], "https://rnb.beta.gouv.fr/activation?status=error"
        )

        # her account is still inactive
        julie.refresh_from_db()
        self.assertFalse(julie.is_active)

    @mock.patch("api_alpha.views.validate_captcha")
    def test_is_active_by_default_in_sandbox(self, mock_validate_captcha):
        with self.settings(ENVIRONMENT="sandbox"):
            data = self.julie_data.copy()
            response = self.client.post("/api/alpha/auth/users/", data)
            self.assertEqual(response.status_code, 201)
            user = User.objects.get(first_name="Julie")
            self.assertTrue(user.is_active)

    @mock.patch("batid.tasks.create_sandbox_user.delay")
    @mock.patch("api_alpha.views.validate_captcha")
    def test_account_creation_forwarded_to_sandbox(
        self, mock_validate_captcha, mock_create_sandbox_user
    ):
        with self.settings(
            ENVIRONMENT="production",
            HAS_SANDBOX=True,
            SANDBOX_URL="https://sandbox.example.test",
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post("/api/alpha/auth/users/", self.julie_data)
                self.assertEqual(response.status_code, 201)

                expected_user_data = self.julie_data.copy()
                expected_user_data.pop("password")
                mock_create_sandbox_user.assert_called_once_with(expected_user_data)

                self.assertTrue(User.objects.filter(first_name="Julie").exists())

    @mock.patch("batid.tasks.create_sandbox_user.delay")
    @mock.patch("api_alpha.views.validate_captcha")
    def test_no_additional_params_are_sent_to_sandbox(
        self, mock_validate_captcha, mock_create_sandbox_user
    ):
        with self.settings(
            ENVIRONMENT="production",
            HAS_SANDBOX=True,
            SANDBOX_URL="https://sandbox.example.test",
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/api/alpha/auth/users/",
                    {**self.julie_data, "captcha_solution": "valid_solution"},
                )
                self.assertEqual(response.status_code, 201)

                expected_user_data = self.julie_data.copy()
                expected_user_data.pop("password")
                mock_create_sandbox_user.assert_called_once_with(expected_user_data)

                self.assertTrue(User.objects.filter(first_name="Julie").exists())
