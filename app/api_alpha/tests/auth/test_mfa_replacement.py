from datetime import timedelta
from unittest import mock

from batid.services.mfa import MFAChange, reset_mfa
from batid.tests.helpers import assert_notified, current_code, wrong_code
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from app.mfa_enforcement import MFAEnforcement

PASSWORD = "Str0ng-Passw0rd-9x!"
BACKUP_CODES = ["k3m7qz2a", "p4n8rx5b"]

REPLACE_SETUP = "/api/alpha/auth/mfa/replace/setup/"
REPLACE_CONFIRM = "/api/alpha/auth/mfa/replace/confirm/"
BACKUP_CODES_PATH = "/api/alpha/auth/mfa/backup_codes/"
NOTIFY_PATH = "batid.tasks.send_mfa_change_notification.delay"


@override_settings(MFA_ENFORCEMENT=MFAEnforcement.OPTIONAL)
class MFAReplacementTest(APITestCase):
    def setUp(self):
        # ScopedRateThrottle counts through the default cache: start from scratch.
        cache.clear()
        self.user = User.objects.create_user(
            username="jdupont", email="jdupont@exemple.fr", password=PASSWORD
        )
        self.app = TOTPDevice.objects.create(user=self.user, name="app", confirmed=True)
        backup_device = StaticDevice.objects.create(user=self.user, name="backup")
        for code in BACKUP_CODES:
            StaticToken.objects.create(device=backup_device, token=code)
        self.token = Token.objects.create(user=self.user)

    def post(self, path, *, otp=None, password=PASSWORD):
        body = {"username": "jdupont", "password": password}
        if otp is not None:
            body["otp"] = otp
        return self.client.post(path, body, format="json")

    def login(self, otp):
        return self.client.post(
            "/api/alpha/login/",
            {"username": "jdupont", "password": PASSWORD, "otp": otp},
            format="json",
        )

    def pending_app(self) -> TOTPDevice:
        return TOTPDevice.objects.get(user=self.user, confirmed=False)

    def backup_codes(self) -> set[str]:
        return set(
            StaticToken.objects.filter(device__user=self.user).values_list(
                "token", flat=True
            )
        )

    def assert_error(self, response, *, status_code, error):
        self.assertEqual(response.status_code, status_code)
        self.assertEqual(response.json()["error"], error)

    def assert_token_works(self):
        self.assertEqual(
            self.client.get(
                "/api/alpha/auth/users/me/tokens",
                HTTP_AUTHORIZATION=f"Token {self.token.key}",
            ).status_code,
            200,
        )

    def assert_replaced(self, response):
        """The confirmation answered 200 with 10 new backup codes only; the pending
        app is now the only app, the old backup codes are gone and the API token
        is unchanged and still works."""
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"backup_codes"})
        self.assertEqual(len(set(body["backup_codes"])), 10)
        self.assertEqual(self.backup_codes(), set(body["backup_codes"]))
        new_app = TOTPDevice.objects.get(user=self.user)
        self.assertNotEqual(new_app.pk, self.app.pk)
        self.assertTrue(new_app.confirmed)
        self.assertEqual(Token.objects.get(user=self.user).key, self.token.key)
        self.assert_token_works()

    def test_replace_with_app_code(self):
        """Replace setup with the current code of the app, then confirm with the
        first code of the new app: 200 with the QR data, then 200 with 10 new
        backup codes and no login_code; the old app and backup codes are deleted and
        the API token still works."""
        setup_response = self.post(REPLACE_SETUP, otp=current_code(self.app))

        self.assertEqual(setup_response.status_code, 200)
        self.assertEqual(
            set(setup_response.json()), {"otpauth_uri", "secret", "qr_code_svg"}
        )
        self.assert_replaced(
            self.post(REPLACE_CONFIRM, otp=current_code(self.pending_app()))
        )

    def test_replace_with_backup_code(self):
        """Replace setup with a backup code, then confirm with the first code of the
        new app: same result as with the app code."""
        self.assertEqual(self.post(REPLACE_SETUP, otp=BACKUP_CODES[0]).status_code, 200)

        self.assert_replaced(
            self.post(REPLACE_CONFIRM, otp=current_code(self.pending_app()))
        )

    def test_setup_wrong_code(self):
        """Replace setup with a wrong app code: 401 mfa_invalid, one throttling
        failure kept on the app (not rolled back), no pending app."""
        response = self.post(REPLACE_SETUP, otp=wrong_code(self.app))

        self.assert_error(response, status_code=401, error="mfa_invalid")
        self.app.refresh_from_db()
        self.assertEqual(self.app.throttling_failure_count, 1)
        self.assertFalse(TOTPDevice.objects.filter(confirmed=False).exists())

    def test_setup_without_code(self):
        """Replace setup with no otp field: 401 mfa_invalid, no pending app."""
        response = self.post(REPLACE_SETUP)

        self.assert_error(response, status_code=401, error="mfa_invalid")
        self.assertFalse(TOTPDevice.objects.filter(confirmed=False).exists())

    def test_replacement_wrong_password(self):
        """Replacement started with a backup code, then replace setup, replace
        confirm (with the new app's code) and regeneration with a wrong password:
        400 non_field_errors each; the pending app stays unconfirmed, the old app
        and the remaining backup code are kept."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        pending = self.pending_app()

        for path, otp in (
            (REPLACE_SETUP, BACKUP_CODES[1]),
            (REPLACE_CONFIRM, current_code(pending)),
            (BACKUP_CODES_PATH, BACKUP_CODES[1]),
        ):
            with self.subTest(path=path):
                response = self.post(path, otp=otp, password="wrong")

                self.assertEqual(response.status_code, 400)
                self.assertIn("non_field_errors", response.json())
        self.assertEqual(self.pending_app().pk, pending.pk)
        self.assertTrue(TOTPDevice.objects.filter(pk=self.app.pk).exists())
        self.assertEqual(self.backup_codes(), {BACKUP_CODES[1]})

    def test_regenerate_with_app_code(self):
        """Regeneration with the current app code: 200 with 10 new backup codes only;
        the old ones are gone, the app is unchanged and the API token still works."""
        response = self.post(BACKUP_CODES_PATH, otp=current_code(self.app))

        self.assertEqual(response.status_code, 200)
        codes = response.json()["backup_codes"]
        self.assertEqual(set(response.json()), {"backup_codes"})
        self.assertEqual(len(set(codes)), 10)
        self.assertEqual(self.backup_codes(), set(codes))
        self.assertEqual(list(TOTPDevice.objects.filter(user=self.user)), [self.app])
        self.assert_token_works()

    def test_regenerate_wrong_code(self):
        """Regeneration with a wrong app code: 401 mfa_invalid, one throttling
        failure kept on the app, the backup codes are unchanged."""
        response = self.post(BACKUP_CODES_PATH, otp=wrong_code(self.app))

        self.assert_error(response, status_code=401, error="mfa_invalid")
        self.app.refresh_from_db()
        self.assertEqual(self.app.throttling_failure_count, 1)
        self.assertEqual(self.backup_codes(), set(BACKUP_CODES))

    def test_setup_consumes_the_backup_code(self):
        """Replace setup with a backup code, replacement then abandoned: the code is
        consumed (one left) and refused at /login/ with 401 mfa_invalid."""
        self.assertEqual(self.post(REPLACE_SETUP, otp=BACKUP_CODES[0]).status_code, 200)

        self.assertEqual(self.backup_codes(), {BACKUP_CODES[1]})
        self.assert_error(
            self.login(BACKUP_CODES[0]), status_code=401, error="mfa_invalid"
        )

    def test_setup_growing_delay(self):
        """Replace setup with a wrong code, then the right code at the same instant:
        refused (1 s delay). A second wrong code 10 s later: the right code is still
        refused 1 s after it (2 s delay), then accepted 3 s after it."""
        start = timezone.now()

        # Fixed clock: the time a call takes must not eat into the delay under test.
        with mock.patch("django.utils.timezone.now") as now:

            def seconds_later(seconds):
                now.return_value = start + timedelta(seconds=seconds)

            seconds_later(0)
            self.post(REPLACE_SETUP, otp=wrong_code(self.app))
            self.assert_error(
                self.post(REPLACE_SETUP, otp=current_code(self.app)),
                status_code=401,
                error="mfa_invalid",
            )

            seconds_later(10)
            self.post(REPLACE_SETUP, otp=wrong_code(self.app))
            self.app.refresh_from_db()
            self.assertEqual(self.app.throttling_failure_count, 2)

            seconds_later(11)
            self.assert_error(
                self.post(REPLACE_SETUP, otp=current_code(self.app)),
                status_code=401,
                error="mfa_invalid",
            )

            seconds_later(13)
            response = self.post(REPLACE_SETUP, otp=current_code(self.app))

        self.assertEqual(response.status_code, 200)

    def test_replace_confirm_growing_delay_on_the_pending_app(self):
        """Replacement started, confirm with a wrong code then the right one at the
        same instant: refused (1 s delay). A second wrong code 10 s later: the right
        code is still refused 1 s after it (2 s delay), then accepted 3 s after it."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        pending = self.pending_app()
        start = timezone.now()

        with mock.patch("django.utils.timezone.now") as now:

            def seconds_later(seconds):
                now.return_value = start + timedelta(seconds=seconds)

            seconds_later(0)
            self.post(REPLACE_CONFIRM, otp=wrong_code(pending))
            self.assert_error(
                self.post(REPLACE_CONFIRM, otp=current_code(pending)),
                status_code=401,
                error="mfa_invalid",
            )

            seconds_later(10)
            self.post(REPLACE_CONFIRM, otp=wrong_code(pending))
            self.assertEqual(self.pending_app().throttling_failure_count, 2)

            seconds_later(11)
            self.assert_error(
                self.post(REPLACE_CONFIRM, otp=current_code(pending)),
                status_code=401,
                error="mfa_invalid",
            )

            seconds_later(13)
            response = self.post(REPLACE_CONFIRM, otp=current_code(pending))

        self.assertEqual(response.status_code, 200)

    def test_replace_confirm_wrong_code(self):
        """Replacement started, confirm with a wrong code: 401 mfa_invalid, one
        throttling failure on the pending app only; both apps are unchanged."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        pending = self.pending_app()

        response = self.post(REPLACE_CONFIRM, otp=wrong_code(pending))

        self.assert_error(response, status_code=401, error="mfa_invalid")
        self.assertEqual(self.pending_app().throttling_failure_count, 1)
        self.app.refresh_from_db()
        self.assertTrue(self.app.confirmed)
        self.assertEqual(self.app.throttling_failure_count, 0)

    def test_replacement_notifies_the_owner(self):
        """Replacement started with a backup code, then confirmed: nothing queued at
        setup, one notification queued after commit at confirmation, for the owner,
        as an app replacement, with the time of the confirmation."""
        with mock.patch(NOTIFY_PATH) as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
            notify.assert_not_called()

            before = timezone.now()
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post(
                    REPLACE_CONFIRM, otp=current_code(self.pending_app())
                )

        self.assertEqual(response.status_code, 200)
        assert_notified(
            test=self,
            notify=notify,
            user=self.user,
            change=MFAChange.APP_REPLACED,
            between=(before, timezone.now()),
        )

    def test_regeneration_notifies_the_owner(self):
        """Regeneration with the current app code: one notification queued after
        commit, for the owner, as a backup codes regeneration, with the time of the
        request."""
        before = timezone.now()
        with mock.patch(NOTIFY_PATH) as notify:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post(BACKUP_CODES_PATH, otp=current_code(self.app))

        self.assertEqual(response.status_code, 200)
        assert_notified(
            test=self,
            notify=notify,
            user=self.user,
            change=MFAChange.BACKUP_CODES_REGENERATED,
            between=(before, timezone.now()),
        )

    def test_refused_changes_notify_no_one(self):
        """Regeneration and replacement confirmation with a wrong code: 401 each,
        no notification queued."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        pending = self.pending_app()

        with mock.patch(NOTIFY_PATH) as notify:
            with self.captureOnCommitCallbacks(execute=True):
                regenerate = self.post(BACKUP_CODES_PATH, otp=wrong_code(self.app))
                confirm = self.post(REPLACE_CONFIRM, otp=wrong_code(pending))

        self.assertEqual(regenerate.status_code, 401)
        self.assertEqual(confirm.status_code, 401)
        notify.assert_not_called()

    def test_enrollment_endpoints_stay_refused_during_a_replacement(self):
        """Replacement started: /auth/mfa/setup/ and /auth/mfa/confirm/ (with the
        pending app's code) answer 409 mfa_already_configured; the pending app is
        the same row, still unconfirmed."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        pending = self.pending_app()

        setup_response = self.post("/api/alpha/auth/mfa/setup/")
        confirm_response = self.post(
            "/api/alpha/auth/mfa/confirm/", otp=current_code(pending)
        )

        for response in (setup_response, confirm_response):
            self.assert_error(response, status_code=409, error="mfa_already_configured")
        self.assertEqual(self.pending_app().pk, pending.pk)

    def test_pending_app_is_refused_at_login(self):
        """Replacement started, the pending app's code sent to /login/, then 10 s
        later (past any delay) as proof to the regeneration: 401 mfa_invalid both
        times, the pending app stays unconfirmed and the backup codes unchanged."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        pending = self.pending_app()
        start = timezone.now()

        with mock.patch("django.utils.timezone.now", return_value=start) as now:
            login_response = self.login(current_code(pending))
            now.return_value = start + timedelta(seconds=10)
            regenerate_response = self.post(
                BACKUP_CODES_PATH, otp=current_code(pending)
            )

        for response in (login_response, regenerate_response):
            self.assert_error(response, status_code=401, error="mfa_invalid")
        self.assertFalse(self.pending_app().confirmed)
        self.assertEqual(self.backup_codes(), {BACKUP_CODES[1]})

    def test_old_app_stays_active_until_confirmation(self):
        """Replacement started with a backup code: /login/ with the current code of
        the old app answers 200 with the token."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])

        response = self.login(current_code(self.app))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token"], self.token.key)

    def test_old_app_code_does_not_confirm(self):
        """Replacement started with a backup code, confirm with the current code of
        the old app: 401 mfa_invalid, the pending app stays unconfirmed and the old
        app is kept."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])

        response = self.post(REPLACE_CONFIRM, otp=current_code(self.app))

        self.assert_error(response, status_code=401, error="mfa_invalid")
        self.assertFalse(self.pending_app().confirmed)
        self.assertTrue(TOTPDevice.objects.filter(pk=self.app.pk).exists())

    def test_refused_without_a_confirmed_app(self):
        """User with backup codes and a pending first enrollment, no confirmed app:
        replace setup and regeneration with a backup code, replace confirm with the
        pending app's code, all answer 400 mfa_setup_not_started; the backup code
        is not consumed and the pending app stays unconfirmed."""
        self.app.delete()
        self.post("/api/alpha/auth/mfa/setup/")
        pending = self.pending_app()

        for path, otp in (
            (REPLACE_SETUP, BACKUP_CODES[0]),
            (REPLACE_CONFIRM, current_code(pending)),
            (BACKUP_CODES_PATH, BACKUP_CODES[0]),
        ):
            with self.subTest(path=path):
                self.assert_error(
                    self.post(path, otp=otp),
                    status_code=400,
                    error="mfa_setup_not_started",
                )
        self.assertEqual(self.backup_codes(), set(BACKUP_CODES))
        self.assertFalse(self.pending_app().confirmed)

    def test_replacement_endpoints_lock_the_user_first(self):
        """Replace setup, replace confirm and regeneration with valid codes: each one
        locks the user row (SELECT ... FOR UPDATE on auth_user) before reading the
        user's apps."""
        with CaptureQueriesContext(connection) as setup_queries:
            self.assertEqual(
                self.post(REPLACE_SETUP, otp=BACKUP_CODES[0]).status_code, 200
            )
        code = current_code(self.pending_app())
        with CaptureQueriesContext(connection) as confirm_queries:
            self.assertEqual(self.post(REPLACE_CONFIRM, otp=code).status_code, 200)
        new_backup_code = next(iter(self.backup_codes()))
        with CaptureQueriesContext(connection) as regenerate_queries:
            self.assertEqual(
                self.post(BACKUP_CODES_PATH, otp=new_backup_code).status_code, 200
            )

        for queries in (setup_queries, confirm_queries, regenerate_queries):
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

    def test_reset_during_a_replacement(self):
        """Replacement started, MFA reset by an admin, then confirm with the pending
        app's code: 400 mfa_setup_not_started, no app and no backup codes left."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])
        code = current_code(self.pending_app())
        reset_mfa(self.user)

        response = self.post(REPLACE_CONFIRM, otp=code)

        self.assert_error(response, status_code=400, error="mfa_setup_not_started")
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())

    def test_replace_confirm_when_the_app_vanishes(self):
        """Replacement started, confirm while the pending app is deleted between the
        code check and the confirmation (verify_token mocked to delete it and
        accept): 400 mfa_setup_not_started, the old app and the remaining backup
        code are kept."""
        self.post(REPLACE_SETUP, otp=BACKUP_CODES[0])

        def delete_and_accept(user, persistent_id, token):
            TOTPDevice.objects.filter(user=user, confirmed=False).delete()
            return True

        with mock.patch("django_otp.verify_token", side_effect=delete_and_accept):
            response = self.post(REPLACE_CONFIRM, otp="123456")

        self.assert_error(response, status_code=400, error="mfa_setup_not_started")
        self.assertEqual(list(TOTPDevice.objects.filter(user=self.user)), [self.app])
        self.assertEqual(self.backup_codes(), {BACKUP_CODES[1]})
