from django.contrib.auth.models import User
from django.test import TestCase

from batid.models import Organization
from batid.models import UserProfile
from batid.services.ads import get_managed_insee_codes
from batid.services.org import populate_organization_on_profiles


class TestRNBUser(TestCase):
    def setUp(self):
        u = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe", email="john@doe.com"
        )
        org_1 = Organization.objects.create(
            name="Test Org", managed_cities=["12345", "67890"]
        )
        org_1.users.add(u)

        org_2 = Organization.objects.create(
            name="Test Org", managed_cities=["42420", "12345"]
        )
        org_2.users.add(u)

    def test_user_can_manage_ads(self):
        u = User.objects.get(username="johndoe")

        managed_codes = get_managed_insee_codes(u)

        managed_codes.sort()

        expected = ["12345", "42420", "67890"]
        expected.sort()

        self.assertListEqual(managed_codes, expected)


class TestPopulateOrganizationOnProfile(TestCase):
    """
    After data migration: UserProfile.organization is set from M2M.
    - A user in exactly one org gets that org assigned.
    - A user in multiple orgs gets one of them assigned (first by pk).
    - A user in no org keeps organization=None.
    """

    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A", managed_cities=["11000"])
        self.org_b = Organization.objects.create(name="Org B", managed_cities=["22000"])

        self.user_one_org = User.objects.create_user(
            username="one_org", email="one_org@test.com"
        )
        UserProfile.objects.create(user=self.user_one_org)
        self.org_a.users.add(self.user_one_org)

        self.user_multi_org = User.objects.create_user(
            username="multi_org", email="multi_org@test.com"
        )
        UserProfile.objects.create(user=self.user_multi_org)
        self.org_a.users.add(self.user_multi_org)
        self.org_b.users.add(self.user_multi_org)

        self.user_no_org = User.objects.create_user(
            username="no_org", email="no_org@test.com"
        )
        UserProfile.objects.create(user=self.user_no_org)

    def test_single_org_user_gets_org_assigned(self):
        populate_organization_on_profiles()
        self.user_one_org.profile.refresh_from_db()
        self.assertEqual(self.user_one_org.profile.organization, self.org_a)

    def test_multi_org_user_gets_first_org_by_pk(self):
        populate_organization_on_profiles()
        self.user_multi_org.profile.refresh_from_db()
        # first org by pk
        self.assertEqual(self.user_multi_org.profile.organization, self.org_a)

    def test_no_org_user_keeps_null(self):
        populate_organization_on_profiles()
        self.user_no_org.profile.refresh_from_db()
        self.assertIsNone(self.user_no_org.profile.organization)
