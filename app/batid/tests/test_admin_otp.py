from unittest import mock

from batid.tests.helpers import current_code, login_with_otp
from batid.views import MetabaseProxyView
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

PASSWORD = "Str0ng-Passw0rd-9x!"


class ProxyCalled(Exception):
    """Raised instead of reaching the upstream server of a proxy view."""


class AdminOTPTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@rnb.fr", password=PASSWORD
        )

    def test_staff_without_otp_is_sent_to_login(self):
        """Superuser logged in without a second factor: /admin/ and the custom
        admin pages (worker, rollback, ADS export) redirect to the login page."""
        self.client.force_login(self.superuser)

        for url in (
            "/admin/",
            "/admin/worker/",
            "/admin/rollback/",
            "/admin/export_ads/",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/admin/login/", response.url, url)

    def test_staff_with_otp(self):
        """Superuser logged in with a verified device: /admin/ answers 200."""
        login_with_otp(client=self.client, user=self.superuser)

        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_admin_login_form(self):
        """POST /admin/login/ with username and password only: the form is shown
        again with the device choice. With the device and its current code: redirect
        and the session holds the verified device."""
        device = TOTPDevice.objects.create(
            user=self.superuser, name="app", confirmed=True
        )

        response = self.client.post(
            "/admin/login/", {"username": "admin", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{device.persistent_id}"')

        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin",
                "password": PASSWORD,
                "otp_device": device.persistent_id,
                "otp_token": current_code(device),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session[DEVICE_ID_SESSION_KEY], device.persistent_id
        )
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_proxies_refuse_unverified_superuser(self):
        """Superuser logged in without a second factor: /flower/ and a non-public
        Metabase URL answer 403."""
        self.client.force_login(self.superuser)

        self.assertEqual(self.client.get("/flower/").status_code, 403)
        self.assertEqual(self.client.get("/metabase/dashboard/1").status_code, 403)

    def proxied_headers(self, url, **headers) -> dict:
        captured = {}

        def capture(view, request, path):
            captured.update(view.request_headers)
            raise ProxyCalled

        with mock.patch.object(
            MetabaseProxyView,
            "_created_proxy_response",
            autospec=True,
            side_effect=capture,
        ):
            # Django logs the exception that stands in for the upstream call
            with self.assertLogs("django.request", "ERROR"):
                with self.assertRaises(ProxyCalled):
                    self.client.get(url, headers=headers)
        return captured

    def test_metabase_remote_user_only_when_verified(self):
        """Public Metabase URL: still proxied for an unverified superuser, without
        X-Remote-User; a verified superuser gets X-Remote-User set to its email."""
        url = "/metabase/public/dashboard/abc"

        self.client.force_login(self.superuser)
        self.assertNotIn("X-Remote-User", self.proxied_headers(url))

        login_with_otp(client=self.client, user=self.superuser)
        self.assertEqual(self.proxied_headers(url)["X-Remote-User"], "admin@rnb.fr")


class ResetMFAActionTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@rnb.fr", password=PASSWORD
        )
        login_with_otp(client=self.client, user=self.admin)

    def test_reset_selected_users_only(self):
        """Admin action "reset_mfa" on two users: their TOTP and static devices
        (with tokens) are deleted; a third user's devices are untouched."""
        selected = [
            User.objects.create_user(username=f"user{i}", email=f"user{i}@exemple.fr")
            for i in range(2)
        ]
        other = User.objects.create_user(username="other", email="other@exemple.fr")
        for user in [*selected, other]:
            TOTPDevice.objects.create(user=user, name="app", confirmed=True)
            static = StaticDevice.objects.create(user=user, name="backup")
            StaticToken.objects.create(device=static, token="k3m7qz2a")

        response = self.client.post(
            "/admin/auth/user/",
            {"action": "reset_mfa", "_selected_action": [u.pk for u in selected]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(TOTPDevice.objects.filter(user__in=selected).exists())
        self.assertFalse(StaticDevice.objects.filter(user__in=selected).exists())
        self.assertTrue(TOTPDevice.objects.filter(user=other).exists())
        self.assertTrue(StaticToken.objects.filter(device__user=other).exists())

    def test_reset_is_logged(self):
        """Admin action "reset_mfa" on one user: one CHANGE entry in the admin history
        of that user, by the admin, with the message "Double authentification
        réinitialisée."; no entry for an unselected user."""
        selected = User.objects.create_user(username="user", email="user@exemple.fr")
        other = User.objects.create_user(username="other", email="other@exemple.fr")

        self.client.post(
            "/admin/auth/user/",
            {"action": "reset_mfa", "_selected_action": [selected.pk]},
        )

        entry = LogEntry.objects.get(object_id=str(selected.pk))
        self.assertEqual(entry.user, self.admin)
        self.assertEqual(entry.action_flag, CHANGE)
        self.assertEqual(entry.change_message, "Double authentification réinitialisée.")
        self.assertFalse(LogEntry.objects.filter(object_id=str(other.pk)).exists())

    def test_reset_locks_the_user_first(self):
        """Admin action "reset_mfa" on one user with a confirmed app: the user row is
        locked (SELECT ... FOR UPDATE on auth_user) before the app is deleted, the same
        lock as setup and confirm, so a reset never deletes an app being confirmed."""
        selected = User.objects.create_user(username="user", email="user@exemple.fr")
        TOTPDevice.objects.create(user=selected, name="app", confirmed=True)

        with CaptureQueriesContext(connection) as queries:
            self.client.post(
                "/admin/auth/user/",
                {"action": "reset_mfa", "_selected_action": [selected.pk]},
            )

        sqls = [query["sql"] for query in queries.captured_queries]
        user_locks = [
            i
            for i, sql in enumerate(sqls)
            if 'FROM "auth_user"' in sql and "FOR UPDATE" in sql
        ]
        device_deletes = [
            i
            for i, sql in enumerate(sqls)
            if sql.startswith('DELETE FROM "otp_totp_totpdevice"')
        ]
        self.assertTrue(user_locks)
        self.assertTrue(device_deletes)
        self.assertLess(user_locks[0], device_deletes[0])
        self.assertFalse(TOTPDevice.objects.filter(user=selected).exists())
