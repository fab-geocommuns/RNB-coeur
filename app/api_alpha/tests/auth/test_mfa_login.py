from datetime import timedelta
from unittest import mock

from batid.tests.helpers import current_code, wrong_code
from batid.utils.constants import ADS_GROUP_NAME
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from app.mfa_enforcement import MFAEnforcement

PASSWORD = "Str0ng-Passw0rd-9x!"


class MFALoginTestCase(APITestCase):
    def setUp(self):
        # ScopedRateThrottle counts through the default cache: start from scratch.
        cache.clear()
        self.user = User.objects.create_user(
            username="jdupont", email="jdupont@exemple.fr", password=PASSWORD
        )

    def add_app(self) -> TOTPDevice:
        return TOTPDevice.objects.create(user=self.user, name="app", confirmed=True)

    def login(self, **extra):
        return self.client.post(
            "/api/alpha/login/",
            {"username": "jdupont", "password": PASSWORD, **extra},
            format="json",
        )


@override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
class LoginWithAppTest(MFALoginTestCase):
    def setUp(self):
        super().setUp()
        self.device = self.add_app()

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OFF)
    def test_off_ignores_the_app(self):
        """OFF, user with a confirmed app, no otp: 200 with the token and no
        mfa_setup_suggested key (behaviour before the second factor)."""
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["token"], Token.objects.get(user=self.user).key
        )
        self.assertNotIn("mfa_setup_suggested", response.json())

    def test_missing_code(self):
        """User with an app, no otp: 401 mfa_required and no token in the body."""
        response = self.login()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_required")
        self.assertNotIn("token", response.json())

    def test_wrong_code_then_growing_delay(self):
        """Wrong otp: 401 mfa_invalid and one recorded failure. The right code sent
        right after is refused too (throttle delay), then accepted once the delay
        has passed."""
        response = self.login(otp=wrong_code(self.device))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")
        self.device.refresh_from_db()
        self.assertEqual(self.device.throttling_failure_count, 1)

        response = self.login(otp=current_code(self.device))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")

        TOTPDevice.objects.filter(pk=self.device.pk).update(
            throttling_failure_timestamp=timezone.now() - timedelta(seconds=10)
        )
        response = self.login(otp=current_code(self.device))
        self.assertEqual(response.status_code, 200)

    def test_valid_code_cannot_be_replayed(self):
        """Valid TOTP code: 200 with the token. The same code sent again: 401
        mfa_invalid."""
        code = current_code(self.device)

        response = self.login(otp=code)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["token"], Token.objects.get(user=self.user).key
        )

        response = self.login(otp=code)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")

    def test_backup_code_is_single_use(self):
        """Backup code sent uppercase with a space: 200. The same code again: 401
        mfa_invalid."""
        backup_device = StaticDevice.objects.create(user=self.user, name="backup")
        StaticToken.objects.create(device=backup_device, token="k3m7qz2a")

        response = self.login(otp="K3M7 QZ2A")
        self.assertEqual(response.status_code, 200)

        response = self.login(otp="k3m7qz2a")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")

    def test_code_of_a_second_app(self):
        """Second confirmed app added by hand: a wrong code is refused (401
        mfa_invalid) with one failure on each app; once the delay has passed, the
        code of the second app gives 200 and clears the failure of the first one."""
        second = TOTPDevice.objects.create(user=self.user, name="app 2", confirmed=True)

        response = self.login(otp=wrong_code(self.device))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")
        for device in (self.device, second):
            device.refresh_from_db()
            self.assertEqual(device.throttling_failure_count, 1)

        TOTPDevice.objects.filter(user=self.user).update(
            throttling_failure_timestamp=timezone.now() - timedelta(seconds=10)
        )
        response = self.login(otp=current_code(second))
        self.assertEqual(response.status_code, 200)
        for device in (self.device, second):
            device.refresh_from_db()
            self.assertEqual(device.throttling_failure_count, 0)

    def test_code_of_a_second_backup_device(self):
        """Two static devices (e.g. an addstatictoken one kept by hand): a code of
        the second one gives 200 and is used up; the first one keeps its code and
        records no failure."""
        first = StaticDevice.objects.create(user=self.user, name="backup")
        StaticToken.objects.create(device=first, token="k3m7qz2a")
        second = StaticDevice.objects.create(user=self.user, name="Backup Code")
        StaticToken.objects.create(device=second, token="p4x6wy3b")

        response = self.login(otp="p4x6wy3b")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StaticToken.objects.filter(device=second).exists())
        self.assertTrue(StaticToken.objects.filter(device=first).exists())
        first.refresh_from_db()
        self.assertEqual(first.throttling_failure_count, 0)

    def test_numeric_backup_code_added_by_hand(self):
        """App plus a 6-digit backup code added by hand (addstatictoken -t 123456):
        the app code gives 200; the backup code gives 200 once, then 401
        mfa_invalid with one failure on the app and one on the backup device."""
        backup_device = StaticDevice.objects.create(user=self.user, name="Backup Code")
        StaticToken.objects.create(device=backup_device, token="123456")

        response = self.login(otp=current_code(self.device))
        self.assertEqual(response.status_code, 200)

        response = self.login(otp="123456")
        self.assertEqual(response.status_code, 200)

        response = self.login(otp="123456")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_invalid")
        for device in (self.device, backup_device):
            device.refresh_from_db()
            self.assertEqual(device.throttling_failure_count, 1)

    def test_app_code_clears_the_backup_codes_delay(self):
        """Three wrong 6-digit codes (each delay waited out) record three failures
        on the backup device; the app code then gives 200 at the first try, and a
        backup code sent right after gives 200 too: no delay left on it."""
        backup_device = StaticDevice.objects.create(user=self.user, name="backup")
        StaticToken.objects.create(device=backup_device, token="k3m7qz2a")
        an_hour_ago = timezone.now() - timedelta(hours=1)

        for _ in range(3):
            TOTPDevice.objects.filter(pk=self.device.pk).update(
                throttling_failure_timestamp=an_hour_ago
            )
            StaticDevice.objects.filter(pk=backup_device.pk).update(
                throttling_failure_timestamp=an_hour_ago
            )
            response = self.login(otp=wrong_code(self.device))
            self.assertEqual(response.json()["error"], "mfa_invalid")
        backup_device.refresh_from_db()
        self.assertEqual(backup_device.throttling_failure_count, 3)

        TOTPDevice.objects.filter(pk=self.device.pk).update(
            throttling_failure_timestamp=an_hour_ago
        )
        response = self.login(otp=current_code(self.device))
        self.assertEqual(response.status_code, 200)

        response = self.login(otp="k3m7qz2a")
        self.assertEqual(response.status_code, 200)


class LoginWithoutAppTest(MFALoginTestCase):
    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.REQUIRED)
    def test_required(self):
        """REQUIRED, user without app: 401 mfa_setup_required, no token."""
        response = self.login()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_setup_required")
        self.assertNotIn("token", response.json())

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
    def test_optional_in_mfa_required_group(self):
        """OPTIONAL, user without app in the "MFA required" group: 401
        mfa_setup_required."""
        group = Group.objects.create(name=settings.MFA_REQUIRED_GROUP_NAME)
        self.user.groups.add(group)

        response = self.login()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "mfa_setup_required")

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
    def test_optional_staff_and_superuser(self):
        """OPTIONAL, user without app flagged is_staff, then is_superuser only: 401
        mfa_setup_required and no token, like the "MFA required" group."""
        for flag in ("is_staff", "is_superuser"):
            with self.subTest(flag=flag):
                User.objects.filter(pk=self.user.pk).update(
                    is_staff=flag == "is_staff", is_superuser=flag == "is_superuser"
                )

                response = self.login()

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["error"], "mfa_setup_required")
                self.assertNotIn("token", response.json())

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OFF)
    def test_off_staff_and_superuser(self):
        """OFF, superuser and staff user without app: 200 with the token and no
        mfa_setup_suggested key."""
        User.objects.filter(pk=self.user.pk).update(is_staff=True, is_superuser=True)

        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())
        self.assertNotIn("mfa_setup_suggested", response.json())

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
    def test_optional_suggests_setup(self):
        """OPTIONAL, user without app and outside the group: 200 with the token and
        mfa_setup_suggested true."""
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())
        self.assertIs(response.json()["mfa_setup_suggested"], True)

    @override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
    def test_backup_codes_alone_are_not_an_app(self):
        """OPTIONAL, user with only a static device (addstatictoken): 200 with
        mfa_setup_suggested true, no code asked."""
        device = StaticDevice.objects.create(user=self.user, name="token")
        StaticToken.objects.create(device=device, token="k3m7qz2a")

        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["mfa_setup_suggested"], True)


# THROTTLE_RATES is bound to the settings dict at import time: patch the rate dict itself.
@mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "2/min"})
class LoginThrottleTest(MFALoginTestCase):
    def post(self, *, path, username):
        return self.client.post(
            path, {"username": username, "password": "wrong"}, format="json"
        )

    def test_counted_per_identifier_across_login_and_setup(self):
        """2/min: a /login/ call for "jdupont" and a /auth/mfa/setup/ call for
        " JDupont " fill the same bucket, the 3rd call for "jdupont" gets 429.
        Another identifier from the same IP still gets through (400)."""
        self.assertEqual(
            self.post(path="/api/alpha/login/", username="jdupont").status_code, 400
        )
        self.assertEqual(
            self.post(
                path="/api/alpha/auth/mfa/setup/", username=" JDupont "
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(path="/api/alpha/login/", username="jdupont").status_code, 429
        )
        self.assertEqual(
            self.post(path="/api/alpha/login/", username="other").status_code, 400
        )

    def test_ip_fallback_without_identifier(self):
        """2/min, no username submitted: counted on the client IP, 3rd call 429."""
        self.assertEqual(
            self.post(path="/api/alpha/login/", username="").status_code, 400
        )
        self.assertEqual(
            self.post(path="/api/alpha/login/", username="").status_code, 400
        )
        self.assertEqual(
            self.post(path="/api/alpha/login/", username="").status_code, 429
        )


@override_settings(MFA_ENFORCEMENT=MFAEnforcement.REQUIRED)
class TokenAuthenticationUnchangedTest(MFALoginTestCase):
    def test_api_token_of_user_with_app(self):
        """REQUIRED, user with a confirmed app: GET /auth/users/me/ with
        `Authorization: Token` answers 200, no code asked."""
        self.add_app()
        token = Token.objects.create(user=self.user)

        response = self.client.get(
            "/api/alpha/auth/users/me/", HTTP_AUTHORIZATION=f"Token {token.key}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "jdupont")

    def test_ads_token(self):
        """REQUIRED, ADS account (unusable password, no app) with its token: GET
        /auth/users/me/ answers 200."""
        ads_user = User.objects.create_user(username="ads_editor")
        ads_user.groups.add(Group.objects.create(name=ADS_GROUP_NAME))
        token = Token.objects.create(user=ads_user)

        response = self.client.get(
            "/api/alpha/auth/users/me/", HTTP_AUTHORIZATION=f"Token {token.key}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["groups"], [ADS_GROUP_NAME])
