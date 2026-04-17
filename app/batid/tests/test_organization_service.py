from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from batid.exceptions import INSEESireneAPIDown
from batid.models import Organization, ProConnectIdentity, UserProfile
from batid.services.organization import link_user_to_organization


class LinkUserToOrganizationTest(TestCase):
    """Tests for link_user_to_organization(user).

    Priority: staff/superuser -> Equipe RNB; SIREN (authoritative, always replayed,
    auto-creates from INSEE); email domain fallback (only when profile.organization is None).
    """

    def _make_user(self, email="user@example.com"):
        user = User.objects.create(username=email.split("@")[0], email=email)
        UserProfile.objects.create(user=user)
        return user

    # --- Staff / superuser ---

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_user_linked_to_rnb_team_org(self):
        """Staff user is always linked to the RNB team org, regardless of SIREN."""
        user = self._make_user()
        user.is_staff = True
        user.save()
        rnb_org = Organization.objects.create(name="Equipe RNB")
        Organization.objects.create(name="Other", siren="130025265")
        ProConnectIdentity.objects.create(user=user, sub="sub-s1", siret="13002526500013")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, rnb_org)

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_superuser_linked_to_rnb_team_org(self):
        """Superuser is always linked to the RNB team org."""
        user = self._make_user()
        user.is_superuser = True
        user.save()
        rnb_org = Organization.objects.create(name="Equipe RNB")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, rnb_org)

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_not_linked_to_siren_org_when_rnb_org_missing(self):
        """Staff user is not linked via SIREN even when the RNB team org is absent from DB."""
        user = self._make_user()
        user.is_staff = True
        user.save()
        Organization.objects.create(name="Other", siren="130025265")
        ProConnectIdentity.objects.create(user=user, sub="sub-s2", siret="13002526500013")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.organization)

    # --- SIREN matching ---

    def test_links_via_siren_match(self):
        """Non-staff user whose ProConnect SIRET[:9] matches org.siren -> profile linked."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-1", siret="13002526500013")
        org = Organization.objects.create(name="DINUM", siren="130025265")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, org)

    @mock.patch("batid.services.organization.fetch_siren_data")
    def test_creates_org_from_insee_when_siren_not_in_db(self, mock_fetch):
        """No org in DB for SIREN -> fetches from INSEE, creates org, links user."""
        mock_fetch.return_value = {
            "uniteLegale": {
                "periodesUniteLegale": [
                    {"dateFin": None, "denominationUniteLegale": "DINUM"}
                ]
            }
        }
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-2", siret="13002526500013")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        org = user.profile.organization
        self.assertIsNotNone(org)
        self.assertEqual(org.name, "DINUM")
        self.assertEqual(org.siren, "130025265")

    @mock.patch("batid.services.organization.fetch_siren_data", return_value=None)
    def test_no_link_when_siren_not_in_db_and_insee_returns_none(self, _mock_fetch):
        """No org in DB and INSEE returns None (404) -> profile.organization stays None."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-3", siret="13002526500013")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.organization)

    @mock.patch("batid.services.organization.fetch_siren_data")
    def test_no_link_when_insee_returns_empty_name(self, mock_fetch):
        """INSEE returns data but no denomination -> org not created, profile unchanged."""
        mock_fetch.return_value = {
            "uniteLegale": {"periodesUniteLegale": [{"dateFin": None}]}
        }
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-4", siret="13002526500013")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.organization)
        self.assertFalse(Organization.objects.filter(siren="130025265").exists())

    def test_siren_updates_org_even_when_one_already_set(self):
        """Calling again with a different SIREN match updates profile.organization."""
        user = self._make_user()
        old_org = Organization.objects.create(name="Old", siren="999999999")
        new_org = Organization.objects.create(name="DINUM", siren="130025265")
        user.profile.organization = old_org
        user.profile.save()
        ProConnectIdentity.objects.create(user=user, sub="sub-5", siret="13002526500013")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, new_org)

    # --- Email domain fallback ---

    def test_links_via_email_domain_when_no_pro_connect_identity(self):
        """User with no ProConnect identity whose email domain matches -> profile linked."""
        user = self._make_user(email="agent@gouv.fr")
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, org)

    def test_siren_takes_priority_over_email_domain(self):
        """SIREN match wins even when email domain also matches a different org."""
        user = self._make_user(email="agent@gouv.fr")
        ProConnectIdentity.objects.create(user=user, sub="sub-6", siret="13002526500013")
        org_siren = Organization.objects.create(name="DINUM", siren="130025265")
        Organization.objects.create(name="Etat", email_domain="gouv.fr")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, org_siren)

    def test_email_domain_not_applied_when_org_already_set(self):
        """Email domain fallback does not override an existing profile.organization."""
        user = self._make_user(email="agent@gouv.fr")
        existing_org = Organization.objects.create(name="Existing", siren="999999999")
        Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user.profile.organization = existing_org
        user.profile.save()

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, existing_org)

    # --- Edge cases ---

    @mock.patch("batid.services.organization.fetch_siren_data", return_value=None)
    def test_no_match_leaves_profile_unchanged(self, _mock_fetch):
        """No matching SIREN or domain -> profile.organization stays None."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-7", siret="99999999900000")
        Organization.objects.create(name="Other", siren="130025265")

        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.organization)

    def test_short_siret_does_not_crash(self):
        """Malformed SIRET (< 9 chars) does not raise and produces no SIREN link."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-8", siret="12345")

        link_user_to_organization(user)  # must not raise

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.organization)

    def test_calling_twice_is_idempotent(self):
        """Calling twice with the same SIREN sets the same org both times."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-9", siret="13002526500013")
        org = Organization.objects.create(name="DINUM", siren="130025265")

        link_user_to_organization(user)
        link_user_to_organization(user)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, org)

    @mock.patch(
        "batid.services.organization.fetch_siren_data",
        side_effect=INSEESireneAPIDown,
    )
    def test_insee_api_error_propagates(self, _mock_fetch):
        """INSEESireneAPIDown raised by INSEE is not suppressed — propagates to caller."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-x", siret="13002526500013")
        with self.assertRaises(INSEESireneAPIDown):
            link_user_to_organization(user)
