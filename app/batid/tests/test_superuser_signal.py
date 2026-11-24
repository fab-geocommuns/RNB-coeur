from io import StringIO
from unittest.mock import patch

from batid.services.tchap import TchapLevel
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase

NEW_SUPERUSER_KWARGS = {
    "level": TchapLevel.ALERT,
    "title": "Nouveau superutilisateur",
    "details": [("Compte", "root")],
}


@patch("batid.signals.notify_tech_or_log")
class NewSuperuser(TestCase):
    def test_create_superuser(self, notify):
        """
        Input: User.objects.create_superuser for "root".
        Expected: once committed, one ALERT "Nouveau superutilisateur" naming root.
        """
        with self.captureOnCommitCallbacks(execute=True):
            User.objects.create_superuser(username="root", email="root@rnb.fr")

        notify.assert_called_once_with(**NEW_SUPERUSER_KWARGS)

    def test_existing_user_promoted(self, notify):
        """
        Input: the existing user "root" saved with is_superuser set to True.
        Expected: one ALERT "Nouveau superutilisateur" naming root.
        """
        user = User.objects.create_user(username="root")

        with self.captureOnCommitCallbacks(execute=True):
            user.is_superuser = True
            user.save()

        notify.assert_called_once_with(**NEW_SUPERUSER_KWARGS)

    def test_superuser_saved_again(self, notify):
        """
        Input: the superuser "root" saved again with its e-mail changed.
        Expected: no message.
        """
        user = User.objects.create_superuser(username="root", email="root@rnb.fr")

        with self.captureOnCommitCallbacks(execute=True):
            user.email = "admin@rnb.fr"
            user.save()

        notify.assert_not_called()

    def test_createsuperuser_command(self, notify):
        """
        Input: the createsuperuser command for "root", without password.
        Expected: one ALERT "Nouveau superutilisateur" naming root.
        """
        with self.captureOnCommitCallbacks(execute=True):
            call_command(
                "createsuperuser",
                "--noinput",
                username="root",
                email="root@rnb.fr",
                stdout=StringIO(),
            )

        notify.assert_called_once_with(**NEW_SUPERUSER_KWARGS)

    def test_sent_after_commit(self, notify):
        """
        Input: "root" promoted to superuser inside a transaction, as the admin
        change form does.
        Expected: no message before the commit, one ALERT naming root after it.
        """
        user = User.objects.create_user(username="root")

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                user.is_superuser = True
                user.save()
                notify.assert_not_called()

        notify.assert_called_once_with(**NEW_SUPERUSER_KWARGS)

    def test_login_save(self, notify):
        """
        Input: the superuser "root" saved with update_fields=["last_login"], as a
        login does.
        Expected: no message and a single query (the update itself).
        """
        user = User.objects.create_superuser(username="root", email="root@rnb.fr")

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertNumQueries(1):
                user.save(update_fields=["last_login"])

        notify.assert_not_called()


class NewSuperuserTchapDown(TestCase):
    @patch("batid.services.tchap.notify_tech", side_effect=Exception("tchap down"))
    def test_tchap_down(self, notify):
        """
        Input: User.objects.create_superuser for "root", the Tchap message raising.
        Expected: the user is saved as superuser, the message was attempted once and
        one ERROR record is logged.
        """
        with self.assertLogs("batid.services.tchap", level="ERROR") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                User.objects.create_superuser(username="root", email="root@rnb.fr")

        self.assertTrue(User.objects.get(username="root").is_superuser)
        notify.assert_called_once()
        self.assertEqual(len(logs.records), 1)
