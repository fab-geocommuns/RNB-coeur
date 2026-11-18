from batid.tests.helpers import login_with_otp
from batid.tests.test_kpi import make_api_log
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_tracking.models import APIRequestLog


class APIRequestLogAdminTest(TestCase):
    def setUp(self):
        superuser = User.objects.create_superuser(
            username="admin", email="admin@rnb.fr", password="pw"
        )
        login_with_otp(client=self.client, user=superuser)
        self.log = make_api_log(timezone.now())

    def test_superuser_cannot_delete(self):
        """
        Superuser POSTs the delete confirmation of a log, then the bulk delete action.
        Expected: 403 then no deletion, the log remains.
        """
        url = reverse(
            "admin:rest_framework_tracking_apirequestlog_delete", args=[self.log.pk]
        )
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)

        self.client.post(
            reverse("admin:rest_framework_tracking_apirequestlog_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [self.log.pk],
                "post": "yes",
            },
        )
        self.assertTrue(APIRequestLog.objects.filter(pk=self.log.pk).exists())

    def test_superuser_cannot_add_or_change(self):
        """
        Superuser GETs the add page, then POSTs a new path on the change page of a log.
        Expected: 403 on both, the log path is unchanged, the change page still
        displays the log.
        """
        add_url = reverse("admin:rest_framework_tracking_apirequestlog_add")
        self.assertEqual(self.client.get(add_url).status_code, 403)

        change_url = reverse(
            "admin:rest_framework_tracking_apirequestlog_change", args=[self.log.pk]
        )
        self.assertContains(self.client.get(change_url), "/api/alpha/buildings/")
        self.assertEqual(
            self.client.post(change_url, {"path": "/forged/"}).status_code, 403
        )
        self.log.refresh_from_db()
        self.assertEqual(self.log.path, "/api/alpha/buildings/")
