from io import StringIO

from batid.models import Organization
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase


class CreateSuperuserTest(TestCase):
    """Tests for the createsuperuser override: on top of the built-in user
    creation, the new superuser must be added to the Contributors group and
    given a UserProfile linked to the RNB team org.
    """

    def _call(self, username="admin", email="admin@example.com"):
        call_command(
            "createsuperuser",
            "--noinput",
            username=username,
            email=email,
            stdout=StringIO(),
        )
        return User.objects.get(username=username)

    def test_adds_user_to_contributors_group(self):
        """A freshly created superuser is added to the Contributors group,
        created if it doesn't already exist."""
        user = self._call()

        self.assertTrue(
            user.groups.filter(name=settings.CONTRIBUTORS_GROUP_NAME).exists()
        )

    def test_creates_profile_linked_to_rnb_team_org(self):
        """The new superuser's profile is linked to the "Équipe RNB" org
        (seeded by migration 0132_create_rnb_team_organization) with
        job_title "Admin"."""
        user = self._call()

        self.assertEqual(user.profile.organization.name, settings.RNB_TEAM_ORG_NAME)
        self.assertEqual(user.profile.job_title, "Admin")

    def test_running_it_twice_does_not_duplicate_the_group(self):
        """Creating a second superuser doesn't create a second Contributors
        group: get_or_create makes the group creation idempotent."""
        self._call(username="admin1", email="admin1@example.com")
        self._call(username="admin2", email="admin2@example.com")

        self.assertEqual(
            Group.objects.filter(name=settings.CONTRIBUTORS_GROUP_NAME).count(), 1
        )

    def test_raises_if_rnb_team_org_is_missing(self):
        """If the RNB team org doesn't exist (e.g. renamed/deleted), the
        command fails loudly instead of silently creating a superuser
        without a profile."""
        Organization.objects.filter(name=settings.RNB_TEAM_ORG_NAME).delete()

        with self.assertRaises(Organization.DoesNotExist):
            self._call()
