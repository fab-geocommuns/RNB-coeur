from batid.models import Organization, UserProfile
from batid.services.ads import get_managed_insee_codes
from django.contrib.auth.models import User
from django.test import TestCase


class TestRNBUser(TestCase):
    def setUp(self):
        u = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe", email="john@doe.com"
        )
        org = Organization.objects.create(
            name="Test Org", managed_cities=["12345", "67890"]
        )
        profile, _ = UserProfile.objects.get_or_create(user=u)
        profile.organization = org
        profile.save(update_fields=["organization"])

    def test_user_can_manage_ads(self):
        """User with one org gets managed cities from that org only."""
        u = User.objects.get(username="johndoe")
        managed_codes = get_managed_insee_codes(u)
        managed_codes.sort()
        self.assertListEqual(managed_codes, ["12345", "67890"])

    def test_user_with_no_profile_returns_empty(self):
        """User with no UserProfile row gets an empty list."""
        u = User.objects.create_user(username="noprofile", email="np@test.com")
        self.assertListEqual(get_managed_insee_codes(u), [])

    def test_user_with_no_org_returns_empty(self):
        """User whose profile has no org assignment gets an empty list."""
        u = User.objects.create_user(username="noordg", email="no@test.com")
        UserProfile.objects.create(user=u)
        self.assertListEqual(get_managed_insee_codes(u), [])
