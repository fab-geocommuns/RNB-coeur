from base64 import b32decode
from unittest import mock
from urllib.parse import quote

from batid.tests.helpers import current_code, wrong_code
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from app.mfa_enforcement import MFAEnforcement

PASSWORD = "Str0ng-Passw0rd-9x!"


@override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
class MFAEnrollmentTest(APITestCase):
    def setUp(self):
        # ScopedRateThrottle counts through the default cache: start from scratch.
        cache.clear()
        self.user = User.objects.create_user(
            username="jdupont", email="jdupont@exemple.fr", password=PASSWORD
        )

    def setup_app(self, password=PASSWORD):
        return self.client.post(
            "/api/alpha/auth/mfa/setup/",
            {"username": "jdupont", "password": password},
            format="json",
        )

    def confirm(self, *, otp, password=PASSWORD):
        return self.client.post(
            "/api/alpha/auth/mfa/confirm/",
            {"username": "jdupont", "password": password, "otp": otp},
            format="json",
        )

    def pending_device(self) -> TOTPDevice:
        return TOTPDevice.objects.get(user=self.user, confirmed=False)

    def test_setup(self):
        """Setup with valid credentials: 200 with an otpauth URI carrying the issuer,
        the base32 secret of the new unconfirmed device and an SVG QR code."""
        response = self.setup_app()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        device = self.pending_device()
        self.assertTrue(body["otpauth_uri"].startswith("otpauth://totp/"))
        self.assertIn(f"issuer={quote(settings.OTP_TOTP_ISSUER)}", body["otpauth_uri"])
        self.assertEqual(b32decode(body["secret"]), device.bin_key)
        self.assertIn("<svg", body["qr_code_svg"])

    def test_setup_twice_replaces_the_pending_app(self):
        """Setup called twice: still one unconfirmed device, with a new key."""
        first_secret = self.setup_app().json()["secret"]
        second_secret = self.setup_app().json()["secret"]

        self.assertNotEqual(first_secret, second_secret)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)
        self.assertEqual(b32decode(second_secret), self.pending_device().bin_key)

    def test_refused_when_an_app_is_confirmed(self):
        """User with a confirmed app: setup and confirm answer 409
        mfa_already_configured and the device is left as is."""
        device = TOTPDevice.objects.create(user=self.user, name="app", confirmed=True)

        setup_response = self.setup_app()
        confirm_response = self.confirm(otp=current_code(device))

        for response in (setup_response, confirm_response):
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"], "mfa_already_configured")
        self.assertEqual(list(TOTPDevice.objects.filter(user=self.user)), [device])

    def test_setup_and_confirm_lock_the_user_first(self):
        """Setup, then confirm with the current code: each one locks the user row
        (SELECT ... FOR UPDATE on auth_user) before reading the user's apps, so a
        setup and a confirm of the same user run one after the other and a setup
        never answers 200 for an app being confirmed."""
        with CaptureQueriesContext(connection) as setup_queries:
            self.assertEqual(self.setup_app().status_code, 200)
        code = current_code(self.pending_device())
        with CaptureQueriesContext(connection) as confirm_queries:
            self.assertEqual(self.confirm(otp=code).status_code, 200)

        for queries in (setup_queries, confirm_queries):
            sqls = [query["sql"] for query in queries.captured_queries]
            user_locks = [
                i
                for i, sql in enumerate(sqls)
                if 'FROM "auth_user"' in sql and "FOR UPDATE" in sql
            ]
            device_reads = [
                i for i, sql in enumerate(sqls) if '"otp_totp_totpdevice"' in sql
            ]
            self.assertTrue(user_locks)
            self.assertLess(user_locks[0], device_reads[0])

    def test_wrong_password(self):
        """Wrong password on setup and confirm: 400 non_field_errors, nothing created."""
        for response in (
            self.setup_app(password="wrong"),
            self.confirm(otp="123456", password="wrong"),
        ):
            self.assertEqual(response.status_code, 400)
            self.assertIn("non_field_errors", response.json())
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_confirm_without_setup(self):
        """Confirm before any setup: 400 mfa_setup_not_started."""
        response = self.confirm(otp="123456")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "mfa_setup_not_started")

    def test_confirm_when_the_app_vanishes(self):
        """Setup, then confirm while the pending app is deleted between the code check
        and the confirmation (verify_token mocked to delete it and accept): 400
        mfa_setup_not_started, no app and no backup codes left."""
        self.setup_app()

        def delete_and_accept(user, persistent_id, token):
            TOTPDevice.objects.filter(user=user).delete()
            return True

        with mock.patch("django_otp.verify_token", side_effect=delete_and_accept):
            response = self.confirm(otp="123456")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "mfa_setup_not_started")
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())

    def test_confirm_wrong_code(self):
        """Confirm with a wrong code: 401 mfa_invalid, the device stays unconfirmed."""
        self.setup_app()

        response = self.confirm(otp=wrong_code(self.pending_device()))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")
        self.assertFalse(self.pending_device().confirmed)

    def test_confirm_takes_the_latest_pending_app(self):
        """Two unconfirmed devices, as left by two concurrent setups, confirm with the
        code of the latest one: 200; the latest one is confirmed, the older one is not.
        """
        older = TOTPDevice.objects.create(user=self.user, name="app", confirmed=False)
        latest = TOTPDevice.objects.create(user=self.user, name="app", confirmed=False)

        response = self.confirm(otp=current_code(latest))

        self.assertEqual(response.status_code, 200)
        latest.refresh_from_db()
        older.refresh_from_db()
        self.assertTrue(latest.confirmed)
        self.assertFalse(older.confirmed)

    def test_confirm_valid_code(self):
        """Confirm with the current code: 200 with the login body and 10 distinct
        backup codes; the app is confirmed, an older static device is replaced by one
        holding these 10 codes, and /login/ now asks for a code."""
        old_backup = StaticDevice.objects.create(user=self.user, name="old")
        self.setup_app()

        response = self.confirm(otp=current_code(self.pending_device()))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token"], Token.objects.get(user=self.user).key)
        self.assertEqual(body["username"], "jdupont")
        self.assertEqual(len(set(body["backup_codes"])), 10)
        self.assertTrue(TOTPDevice.objects.get(user=self.user).confirmed)
        self.assertFalse(StaticDevice.objects.filter(pk=old_backup.pk).exists())
        backup_device = StaticDevice.objects.get(user=self.user)
        self.assertEqual(
            set(
                StaticToken.objects.filter(device=backup_device).values_list(
                    "token", flat=True
                )
            ),
            set(body["backup_codes"]),
        )

        login_response = self.client.post(
            "/api/alpha/login/",
            {"username": "jdupont", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login_response.status_code, 401)
        self.assertEqual(login_response.json()["error"], "mfa_required")

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OFF)
    def test_enrollment_available_when_off(self):
        """OFF: setup then confirm with the current code both answer 200."""
        self.assertEqual(self.setup_app().status_code, 200)

        response = self.confirm(otp=current_code(self.pending_device()))

        self.assertEqual(response.status_code, 200)


class CurrentUserTest(APITestCase):
    def test_with_token(self):
        """GET /auth/users/me/ with a valid token: 200 with id, token, username and
        groups."""
        user = User.objects.create_user(username="jdupont", password=PASSWORD)
        token = Token.objects.create(user=user)

        response = self.client.get(
            "/api/alpha/auth/users/me/", HTTP_AUTHORIZATION=f"Token {token.key}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"id": user.id, "token": token.key, "username": "jdupont", "groups": []},
        )

    def test_without_token(self):
        """GET /auth/users/me/ without token: 401."""
        response = self.client.get("/api/alpha/auth/users/me/")

        self.assertEqual(response.status_code, 401)
