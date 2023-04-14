from django.contrib.auth.models import User
from django.test import TestCase

from batid.models import Organization
from batid.logic.user import RNBUser


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

        rnbuser = RNBUser(u)
        managed_codes = rnbuser.get_managed_insee_codes()

        managed_codes.sort()

        expected = ["12345", "42420", "67890"]
        expected.sort()

        self.assertListEqual(managed_codes, expected)
