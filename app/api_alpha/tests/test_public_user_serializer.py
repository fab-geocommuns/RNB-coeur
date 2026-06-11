from api_alpha.serializers.public_user import PublicUserSerializer
from batid.models import Organization, UserProfile
from django.contrib.auth.models import User
from django.test import TestCase


class PublicUserSerializerTest(TestCase):
    def test_user_with_organization_shortname(self):
        """
        Input: a user whose organization has both a name and a short_name.
        Expected: the representation contains organization_name and organization_shortname.
        """
        user = User.objects.create_user(username="julie")
        org = Organization.objects.create(name="Mairie de Dreux", short_name="Dreux")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.organization = org
        profile.save(update_fields=["organization"])
        user.refresh_from_db()

        data = PublicUserSerializer().to_representation(user)

        self.assertEqual(data["organization_name"], "Mairie de Dreux")
        self.assertEqual(data["organization_shortname"], "Dreux")

    def test_user_with_organization_without_shortname(self):
        """
        Input: a user whose organization has a name but no short_name.
        Expected: organization_shortname is None, organization_name is set.
        """
        user = User.objects.create_user(username="julie")
        org = Organization.objects.create(name="Mairie de Dreux")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.organization = org
        profile.save(update_fields=["organization"])
        user.refresh_from_db()

        data = PublicUserSerializer().to_representation(user)

        self.assertEqual(data["organization_name"], "Mairie de Dreux")
        self.assertIsNone(data["organization_shortname"])

    def test_user_without_organization(self):
        """
        Input: a user with a profile but no organization.
        Expected: organization_name and organization_shortname are None.
        """
        user = User.objects.create_user(username="julie")
        UserProfile.objects.get_or_create(user=user)
        user.refresh_from_db()

        data = PublicUserSerializer().to_representation(user)

        self.assertIsNone(data["organization_name"])
        self.assertIsNone(data["organization_shortname"])

    def test_none_user(self):
        """
        Input: None instead of a user instance (anonymous contribution).
        Expected: organization_shortname is None, no exception raised.
        """
        data = PublicUserSerializer().to_representation(None)

        self.assertIsNone(data["organization_shortname"])
