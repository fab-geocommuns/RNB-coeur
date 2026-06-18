from unittest import mock

from batid.exceptions import INSEESireneAPIDown
from batid.models import Organization, ProConnectIdentity, UserProfile
from batid.services.organization import (
    link_organization_to_users,
    link_user_to_organization,
)
from django.contrib.auth.models import User
from django.test import TestCase, override_settings


class LinkUserToOrganizationTest(TestCase):
    """Tests for link_user_to_organization(user).

    Priority: staff/superuser -> Equipe RNB; SIREN (authoritative, always replayed,
    auto-creates from INSEE); email domain fallback (only when user has no org yet).
    Membership is tracked via UserProfile.organization FK.
    """

    def _make_user(self, email="user@example.com"):
        user = User.objects.create(username=email.split("@")[0], email=email)
        UserProfile.objects.create(user=user)
        return user

    def _user_in_org(self, user, org):
        return org.user_profiles.filter(user=user).exists()

    def _set_user_org(self, user, org):
        user.profile.organization = org
        user.profile.save()

    # --- Staff / superuser ---

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_user_linked_to_rnb_team_org(self):
        """Staff user is always added to the RNB team org, regardless of SIREN."""
        user = self._make_user()
        user.is_staff = True
        user.save()
        rnb_org = Organization.objects.create(name="Equipe RNB")
        Organization.objects.create(name="Other", siren="130025265")
        ProConnectIdentity.objects.create(
            user=user, sub="sub-s1", siret="13002526500013"
        )

        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, rnb_org))

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_superuser_linked_to_rnb_team_org(self):
        """Superuser is always added to the RNB team org."""
        user = self._make_user()
        user.is_superuser = True
        user.save()
        rnb_org = Organization.objects.create(name="Equipe RNB")

        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, rnb_org))

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_not_linked_to_siren_org_when_rnb_org_missing(self):
        """Staff user is not linked via SIREN even when the RNB team org is absent from DB."""
        user = self._make_user()
        user.is_staff = True
        user.save()
        siren_org = Organization.objects.create(name="Other", siren="130025265")
        ProConnectIdentity.objects.create(
            user=user, sub="sub-s2", siret="13002526500013"
        )

        link_user_to_organization(user)

        self.assertFalse(self._user_in_org(user, siren_org))
        self.assertFalse(Organization.objects.filter(user_profiles__user=user).exists())

    # --- SIREN matching ---

    def test_links_via_siren_match(self):
        """Non-staff user whose ProConnect SIRET[:9] matches org.siren -> added to org."""
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )
        org = Organization.objects.create(name="DINUM", siren="130025265")

        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, org))

    @mock.patch("batid.services.organization.fetch_siren_data")
    def test_creates_org_from_insee_when_siren_not_in_db(self, mock_fetch):
        """No org in DB for SIREN -> fetches from INSEE, creates org, adds user."""
        mock_fetch.return_value = {
            "uniteLegale": {
                "periodesUniteLegale": [
                    {"dateFin": None, "denominationUniteLegale": "DINUM"}
                ]
            }
        }
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-2", siret="13002526500013"
        )

        link_user_to_organization(user)

        org = Organization.objects.filter(siren="130025265").first()
        self.assertIsNotNone(org)
        self.assertEqual(org.name, "DINUM")
        self.assertTrue(self._user_in_org(user, org))

    @mock.patch("batid.services.organization.fetch_siren_data", return_value=None)
    def test_no_link_when_siren_not_in_db_and_insee_returns_none(self, _mock_fetch):
        """No org in DB and INSEE returns None -> user not added to any org."""
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-3", siret="13002526500013"
        )

        link_user_to_organization(user)

        self.assertFalse(Organization.objects.filter(user_profiles__user=user).exists())

    @mock.patch("batid.services.organization.fetch_siren_data")
    def test_no_link_when_insee_returns_empty_name(self, mock_fetch):
        """INSEE returns data but no denomination -> org not created, user not linked."""
        mock_fetch.return_value = {
            "uniteLegale": {"periodesUniteLegale": [{"dateFin": None}]}
        }
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-4", siret="13002526500013"
        )

        link_user_to_organization(user)

        self.assertFalse(Organization.objects.filter(user_profiles__user=user).exists())
        self.assertFalse(Organization.objects.filter(siren="130025265").exists())

    def test_siren_links_user_even_when_already_in_another_org(self):
        """SIREN match adds user to new org even when they already belong to another."""
        user = self._make_user()
        old_org = Organization.objects.create(name="Old", siren="999999999")
        new_org = Organization.objects.create(name="DINUM", siren="130025265")
        self._set_user_org(user, old_org)
        ProConnectIdentity.objects.create(
            user=user, sub="sub-5", siret="13002526500013"
        )

        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, new_org))

    # --- Email domain fallback ---

    def test_links_via_email_domain_when_no_pro_connect_identity(self):
        """User with no ProConnect identity whose email domain matches -> added to org."""
        user = self._make_user(email="agent@gouv.fr")
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")

        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, org))

    def test_siren_takes_priority_over_email_domain(self):
        """SIREN match wins even when email domain also matches a different org."""
        user = self._make_user(email="agent@gouv.fr")
        ProConnectIdentity.objects.create(
            user=user, sub="sub-6", siret="13002526500013"
        )
        org_siren = Organization.objects.create(name="DINUM", siren="130025265")
        org_domain = Organization.objects.create(name="Etat", email_domain="gouv.fr")

        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, org_siren))
        self.assertFalse(self._user_in_org(user, org_domain))

    def test_email_domain_not_applied_when_user_already_has_org(self):
        """Email domain fallback does not add user to another org if already linked."""
        user = self._make_user(email="agent@gouv.fr")
        existing_org = Organization.objects.create(name="Existing", siren="999999999")
        domain_org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        self._set_user_org(user, existing_org)

        link_user_to_organization(user)

        self.assertFalse(self._user_in_org(user, domain_org))

    # --- Edge cases ---

    @mock.patch("batid.services.organization.fetch_siren_data", return_value=None)
    def test_no_match_leaves_user_unlinked(self, _mock_fetch):
        """No matching SIREN or domain -> user not added to any org."""
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-7", siret="99999999900000"
        )
        Organization.objects.create(name="Other", siren="130025265")

        link_user_to_organization(user)

        self.assertFalse(Organization.objects.filter(user_profiles__user=user).exists())

    def test_short_siret_does_not_crash(self):
        """Malformed SIRET (< 9 chars) does not raise and produces no SIREN link."""
        user = self._make_user()
        ProConnectIdentity.objects.create(user=user, sub="sub-8", siret="12345")

        link_user_to_organization(user)  # must not raise

        self.assertFalse(Organization.objects.filter(user_profiles__user=user).exists())

    def test_calling_twice_is_idempotent(self):
        """Calling twice with the same SIREN sets the org FK once (idempotent)."""
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-9", siret="13002526500013"
        )
        org = Organization.objects.create(name="DINUM", siren="130025265")

        link_user_to_organization(user)
        link_user_to_organization(user)

        self.assertTrue(self._user_in_org(user, org))
        self.assertEqual(org.user_profiles.filter(user=user).count(), 1)

    @mock.patch(
        "batid.services.organization.fetch_siren_data",
        side_effect=INSEESireneAPIDown,
    )
    def test_insee_api_error_propagates(self, _mock_fetch):
        """INSEESireneAPIDown raised by INSEE is not suppressed — propagates to caller."""
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-x", siret="13002526500013"
        )
        with self.assertRaises(INSEESireneAPIDown):
            link_user_to_organization(user)


class LinkUserOrgEnrichmentTest(TestCase):
    """Tests for the candidate-matching & enrichment logic of the SIREN branch of
    link_user_to_organization(user).

    A single OR query (Q(siren) | Q(email_domain)) yields 0, 1 or 2 already-deduplicated
    candidate orgs. 0 -> create from INSEE; 1 -> link + fill empty siren/email_domain
    (never the name); 2 -> link to the SIREN one, no enrichment. Goal: stop creating
    duplicate orgs when one already exists under the user's email domain.
    """

    def _make_user(self, email="agent@dinum.fr"):
        user = User.objects.create(username=email.split("@")[0], email=email)
        UserProfile.objects.create(user=user)
        ProConnectIdentity.objects.create(
            user=user, sub=f"sub-{email}", siret="13002526500013"
        )
        return user

    def _user_in_org(self, user, org):
        return org.user_profiles.filter(user=user).exists()

    def test_email_domain_org_adopts_siren(self):
        """Single candidate matched by email_domain, with no siren: user ProConnect with
        that domain is linked, the org receives the SIREN, its name is untouched, and no
        new org is created."""
        org = Organization.objects.create(name="DINUM manuelle", email_domain="dinum.fr")
        count_before = Organization.objects.count()

        user = self._make_user(email="agent@dinum.fr")
        link_user_to_organization(user)

        org.refresh_from_db()
        self.assertTrue(self._user_in_org(user, org))
        self.assertEqual(org.siren, "130025265")
        self.assertEqual(org.name, "DINUM manuelle")
        self.assertEqual(Organization.objects.count(), count_before)

    def test_siren_org_adopts_email_domain(self):
        """Single candidate matched by siren, with no email_domain: the org receives the
        user's email domain."""
        org = Organization.objects.create(name="DINUM", siren="130025265")

        user = self._make_user(email="agent@dinum.fr")
        link_user_to_organization(user)

        org.refresh_from_db()
        self.assertTrue(self._user_in_org(user, org))
        self.assertEqual(org.email_domain, "dinum.fr")

    def test_single_complete_candidate_unchanged(self):
        """Single candidate already carrying both the right siren and email_domain: user
        is linked and nothing on the org changes."""
        org = Organization.objects.create(
            name="DINUM", siren="130025265", email_domain="dinum.fr"
        )

        user = self._make_user(email="agent@dinum.fr")
        link_user_to_organization(user)

        org.refresh_from_db()
        self.assertTrue(self._user_in_org(user, org))
        self.assertEqual(org.siren, "130025265")
        self.assertEqual(org.email_domain, "dinum.fr")

    def test_two_distinct_candidates_links_to_siren_one(self):
        """Two distinct candidates (one by siren, one by email_domain): user is linked to
        the SIREN org, neither org is modified, no org is created."""
        org_siren = Organization.objects.create(name="DINUM siren", siren="130025265")
        org_domain = Organization.objects.create(
            name="DINUM domaine", email_domain="dinum.fr"
        )
        count_before = Organization.objects.count()

        user = self._make_user(email="agent@dinum.fr")
        link_user_to_organization(user)

        org_siren.refresh_from_db()
        org_domain.refresh_from_db()
        self.assertTrue(self._user_in_org(user, org_siren))
        self.assertFalse(self._user_in_org(user, org_domain))
        self.assertIsNone(org_siren.email_domain)
        self.assertIsNone(org_domain.siren)
        self.assertEqual(Organization.objects.count(), count_before)

    @mock.patch("batid.services.organization.fetch_siren_data")
    def test_zero_candidate_creates_from_insee(self, mock_fetch):
        """No candidate matches siren nor email domain: org is created from INSEE."""
        mock_fetch.return_value = {
            "uniteLegale": {
                "periodesUniteLegale": [
                    {"dateFin": None, "denominationUniteLegale": "DINUM"}
                ]
            }
        }
        user = self._make_user(email="agent@nomatch.fr")
        link_user_to_organization(user)

        org = Organization.objects.filter(siren="130025265").first()
        self.assertIsNotNone(org)
        self.assertEqual(org.name, "DINUM")
        self.assertTrue(self._user_in_org(user, org))

    def test_existing_email_domain_not_overwritten(self):
        """Single candidate (by siren) already carrying a different email_domain: the
        user's domain does not overwrite it."""
        org = Organization.objects.create(
            name="DINUM", siren="130025265", email_domain="other.fr"
        )

        user = self._make_user(email="agent@dinum.fr")
        link_user_to_organization(user)

        org.refresh_from_db()
        self.assertTrue(self._user_in_org(user, org))
        self.assertEqual(org.email_domain, "other.fr")


class LinkOrganizationToUsersTest(TestCase):
    """Tests for link_organization_to_users(org).

    Priority: SIREN (authoritative, overrides existing org); email domain fallback
    (only when user has no org yet). Staff and superusers are skipped unless the org
    is the RNB team.
    """

    def _make_user(self, email="user@example.com", is_staff=False, is_superuser=False):
        user = User.objects.create(
            username=email.split("@")[0],
            email=email,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        UserProfile.objects.create(user=user)
        return user

    def _user_in_org(self, user, org):
        return org.user_profiles.filter(user=user).exists()

    def _set_user_org(self, user, org):
        user.profile.organization = org
        user.profile.save()

    # --- SIREN matching ---

    def test_links_users_via_siren_match(self):
        """Users whose ProConnect SIRET starts with org.siren are linked to the org."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user, org))

    def test_siren_links_multiple_users(self):
        """All users with a matching SIRET are linked, not just the first one."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user_a = self._make_user("a@example.com")
        user_b = self._make_user("b@example.com")
        ProConnectIdentity.objects.create(
            user=user_a, sub="sub-a", siret="13002526500013"
        )
        ProConnectIdentity.objects.create(
            user=user_b, sub="sub-b", siret="13002526500099"
        )

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user_a, org))
        self.assertTrue(self._user_in_org(user_b, org))

    def test_siren_links_user_even_when_already_in_another_org(self):
        """SIREN match reassigns user even when they already belong to another org."""
        old_org = Organization.objects.create(name="Old", siren="999999999")
        new_org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user()
        self._set_user_org(user, old_org)
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_organization_to_users(new_org)

        self.assertTrue(self._user_in_org(user, new_org))

    def test_siren_does_not_link_unrelated_user(self):
        """User with a SIRET from a different SIREN is not linked."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="99999999900000"
        )

        link_organization_to_users(org)

        self.assertFalse(self._user_in_org(user, org))

    def test_siren_skips_staff_users(self):
        """Staff users with a matching SIRET are not linked."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user(is_staff=True)
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_organization_to_users(org)

        self.assertFalse(self._user_in_org(user, org))

    def test_siren_skips_superusers(self):
        """Superusers with a matching SIRET are not linked."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user(is_superuser=True)
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_organization_to_users(org)

        self.assertFalse(self._user_in_org(user, org))

    def test_no_siren_on_org_skips_siren_step(self):
        """Org with no SIREN: the SIREN step is a no-op, no user is linked by SIREN."""
        org = Organization.objects.create(name="DINUM", email_domain="dinum.fr")
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_organization_to_users(org)

        self.assertFalse(self._user_in_org(user, org))

    # --- Email domain fallback ---

    def test_links_users_via_email_domain(self):
        """Users whose email domain matches org.email_domain and have no org are linked."""
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user = self._make_user(email="agent@gouv.fr")

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user, org))

    def test_email_domain_links_multiple_users(self):
        """All matching users without an org are linked, not just the first one."""
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user_a = self._make_user(email="alice@gouv.fr")
        user_b = self._make_user(email="bob@gouv.fr")

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user_a, org))
        self.assertTrue(self._user_in_org(user_b, org))

    def test_email_domain_skips_user_with_existing_org(self):
        """User already linked to an org is not reassigned via email domain."""
        existing_org = Organization.objects.create(name="Other", siren="999999999")
        domain_org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user = self._make_user(email="agent@gouv.fr")
        self._set_user_org(user, existing_org)

        link_organization_to_users(domain_org)

        self.assertFalse(self._user_in_org(user, domain_org))
        self.assertTrue(self._user_in_org(user, existing_org))

    def test_email_domain_links_user_without_profile(self):
        """User with no UserProfile and a matching email is linked (profile is created)."""
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user = User.objects.create(username="agent", email="agent@gouv.fr")

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user, org))

    def test_email_domain_skips_staff_users(self):
        """Staff users with a matching email domain are not linked."""
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user = self._make_user(email="agent@gouv.fr", is_staff=True)

        link_organization_to_users(org)

        self.assertFalse(self._user_in_org(user, org))

    def test_no_email_domain_on_org_skips_email_step(self):
        """Org with no email_domain: the email step is a no-op."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user(email="agent@dinum.fr")

        link_organization_to_users(org)

        self.assertFalse(self._user_in_org(user, org))

    # --- RNB team includes staff and superusers ---

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_user_linked_unconditionally_to_rnb_team(self):
        """Staff user is linked to the RNB team even without a SIREN or email domain match."""
        org = Organization.objects.create(name="Equipe RNB")
        user = self._make_user(is_staff=True)

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user, org))

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_superuser_linked_unconditionally_to_rnb_team(self):
        """Superuser is linked to the RNB team even without a SIREN or email domain match."""
        org = Organization.objects.create(name="Equipe RNB")
        user = self._make_user(is_superuser=True)

        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user, org))

    # --- Idempotency ---

    def test_calling_twice_is_idempotent(self):
        """Calling twice with the same SIREN assigns the org once (idempotent)."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_organization_to_users(org)
        link_organization_to_users(org)

        self.assertTrue(self._user_in_org(user, org))
        self.assertEqual(org.user_profiles.filter(user=user).count(), 1)


class LinkSymmetryTest(TestCase):
    """Symmetry between link_user_to_organization and link_organization_to_users.

    For every matching (user, org) pair, either function should produce the same
    outcome. Intentional asymmetries (staff users) are documented explicitly.
    """

    def _make_user(self, email="user@example.com", is_staff=False, is_superuser=False):
        user = User.objects.create(
            username=email.split("@")[0],
            email=email,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        UserProfile.objects.create(user=user)
        return user

    def _user_in_org(self, user, org):
        return org.user_profiles.filter(user=user).exists()

    def _clear_user_org(self, user):
        user.profile.organization = None
        user.profile.save()

    # --- Symmetry: SIREN match ---

    def test_siren_match_is_symmetric(self):
        """SIREN match: user ends up in org regardless of which function is called."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        link_user_to_organization(user)
        self.assertTrue(
            self._user_in_org(user, org), "link_user_to_organization failed"
        )

        self._clear_user_org(user)

        link_organization_to_users(org)
        self.assertTrue(
            self._user_in_org(user, org), "link_organization_to_users failed"
        )

    # --- Symmetry: email domain match ---

    def test_email_domain_match_is_symmetric(self):
        """Email domain match, user has no org: both functions link the user."""
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user = self._make_user(email="agent@gouv.fr")

        link_user_to_organization(user)
        self.assertTrue(
            self._user_in_org(user, org), "link_user_to_organization failed"
        )

        self._clear_user_org(user)

        link_organization_to_users(org)
        self.assertTrue(
            self._user_in_org(user, org), "link_organization_to_users failed"
        )

    def test_email_domain_no_override_is_symmetric(self):
        """Email domain, user already has an org: neither function reassigns via email."""
        existing_org = Organization.objects.create(name="Other", siren="999999999")
        domain_org = Organization.objects.create(name="Etat", email_domain="gouv.fr")
        user = self._make_user(email="agent@gouv.fr")
        user.profile.organization = existing_org
        user.profile.save()

        link_user_to_organization(user)
        self.assertFalse(
            self._user_in_org(user, domain_org),
            "link_user_to_organization wrongly reassigned via email",
        )

        link_organization_to_users(domain_org)
        self.assertFalse(
            self._user_in_org(user, domain_org),
            "link_organization_to_users wrongly reassigned via email",
        )

    # --- Staff: symmetric for RNB team, asymmetric for other orgs ---

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_user_and_rnb_team_is_symmetric(self):
        """RNB team org: both functions link a staff user to it."""
        rnb_org = Organization.objects.create(name="Equipe RNB")
        user = self._make_user(is_staff=True)

        link_user_to_organization(user)
        self.assertTrue(
            self._user_in_org(user, rnb_org), "link_user_to_organization failed"
        )

        self._clear_user_org(user)

        link_organization_to_users(rnb_org)
        self.assertTrue(
            self._user_in_org(user, rnb_org), "link_organization_to_users failed"
        )

    @override_settings(RNB_TEAM_ORG_NAME="Equipe RNB")
    def test_staff_user_and_non_rnb_org_is_asymmetric(self):
        """Non-RNB org: link_user_to_organization sends staff to RNB team;
        link_organization_to_users skips staff entirely."""
        rnb_org = Organization.objects.create(name="Equipe RNB")
        other_org = Organization.objects.create(name="Other", email_domain="gouv.fr")
        user = self._make_user(email="agent@gouv.fr", is_staff=True)

        link_user_to_organization(user)
        self.assertTrue(self._user_in_org(user, rnb_org))
        self.assertFalse(self._user_in_org(user, other_org))

        self._clear_user_org(user)

        link_organization_to_users(other_org)
        self.assertFalse(self._user_in_org(user, other_org))
        self.assertFalse(self._user_in_org(user, rnb_org))


class OrgSaveSignalTest(TestCase):
    """Signal: link_organization_to_users fires on every Organization save."""

    def _make_user(self, email="user@example.com"):
        user = User.objects.create(username=email.split("@")[0], email=email)
        UserProfile.objects.create(user=user)
        return user

    def _user_in_org(self, user, org):
        return org.user_profiles.filter(user=user).exists()

    def test_creating_org_with_siren_links_matching_users(self):
        """Creating an org with a siren immediately links users with a matching SIRET."""
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        org = Organization.objects.create(name="DINUM", siren="130025265")

        self.assertTrue(self._user_in_org(user, org))

    def test_creating_org_with_email_domain_links_matching_users(self):
        """Creating an org with email_domain immediately links users with a matching email."""
        user = self._make_user(email="agent@gouv.fr")

        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")

        self.assertTrue(self._user_in_org(user, org))

    def test_saving_org_links_newly_matching_users(self):
        """Saving an org (e.g. after adding a siren) links users who now match."""
        org = Organization.objects.create(name="DINUM")
        user = self._make_user()
        ProConnectIdentity.objects.create(
            user=user, sub="sub-1", siret="13002526500013"
        )

        org.siren = "130025265"
        org.save()

        self.assertTrue(self._user_in_org(user, org))
