from batid.models import Organization, UserProfile
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class UserCreationForm(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="foobar", email="foo@bar.com", password="barbaz"
        )
        self.client.force_login(user=self.user)

    def test_has_email_field(self):
        response = self.client.get("/admin/auth/user/add/")
        self.assertContains(response, "email")


class OrganizationMergeAdminTest(TestCase):
    """Tests for the admin organization merge tool.

    The viewed org is the surviving target; an absorbed org is chosen, its user profiles
    are moved onto the target, field values are reconciled, and the absorbed org is
    deleted — all in one atomic POST.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@rnb.fr", password="pw"
        )
        self.client.force_login(self.admin)

    def _merge_url(self, target):
        return reverse("admin:batid_organization_merge", args=[target.pk])

    def _make_user(self, email, org):
        user = User.objects.create(username=email.split("@")[0], email=email)
        UserProfile.objects.create(user=user, organization=org)
        return user

    def _post(self, target, absorbed, **fields):
        payload = {
            "absorbed": absorbed.pk,
            "confirm": "1",
            "name": target.name,
            "short_name": "",
            "siren": "",
            "email_domain": "",
            "managed_cities": "",
        }
        payload.update(fields)
        return self.client.post(self._merge_url(target), payload, follow=True)

    def test_merge_moves_profiles_and_deletes_absorbed(self):
        """Nominal merge: every UserProfile from both orgs points to the target, the
        absorbed org is deleted, and a success message is shown."""
        target = Organization.objects.create(name="Cible")
        absorbed = Organization.objects.create(name="Absorbee")
        u1 = self._make_user("a@example.com", target)
        u2 = self._make_user("b@example.com", absorbed)

        self._post(target, absorbed)

        u1.profile.refresh_from_db()
        u2.profile.refresh_from_db()
        self.assertEqual(u1.profile.organization_id, target.pk)
        self.assertEqual(u2.profile.organization_id, target.pk)
        self.assertFalse(Organization.objects.filter(pk=absorbed.pk).exists())

    def test_merge_blocked_when_different_sirens(self):
        """Target and absorbed both carry non-empty, different SIRENs: the merge is
        refused and nothing is modified."""
        target = Organization.objects.create(name="Cible", siren="111111111")
        absorbed = Organization.objects.create(name="Absorbee", siren="222222222")
        u2 = self._make_user("b@example.com", absorbed)

        self._post(target, absorbed, siren="111111111")

        self.assertTrue(Organization.objects.filter(pk=absorbed.pk).exists())
        u2.profile.refresh_from_db()
        self.assertEqual(u2.profile.organization_id, absorbed.pk)

    def test_merge_applies_chosen_email_domain_without_unique_conflict(self):
        """Admin keeps the absorbed org's email_domain for the target: it is applied
        (absorbed deleted first, so no unique-constraint conflict)."""
        target = Organization.objects.create(name="Cible")
        absorbed = Organization.objects.create(name="Absorbee", email_domain="dinum.fr")

        self._post(target, absorbed, email_domain="dinum.fr")

        target.refresh_from_db()
        self.assertEqual(target.email_domain, "dinum.fr")
        self.assertFalse(Organization.objects.filter(pk=absorbed.pk).exists())

    def test_merge_fills_empty_target_field(self):
        """Target without a SIREN, absorbed with one: the target receives the chosen
        SIREN."""
        target = Organization.objects.create(name="Cible")
        absorbed = Organization.objects.create(name="Absorbee", siren="130025265")

        self._post(target, absorbed, siren="130025265")

        target.refresh_from_db()
        self.assertEqual(target.siren, "130025265")
        self.assertFalse(Organization.objects.filter(pk=absorbed.pk).exists())
