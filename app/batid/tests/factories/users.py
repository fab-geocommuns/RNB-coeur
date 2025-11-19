import factory

from django.contrib.auth.models import User, Group
from rest_framework.authtoken.models import Token

from batid.models import UserProfile
from batid.utils.constants import ADS_GROUP_NAME
from api_alpha.permissions import RNBContributorPermission


class UserProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserProfile


class TokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Token


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    username = factory.Faker("user_name")
    email = factory.Faker("email")
    password = factory.Faker("password")

    profile = factory.RelatedFactory(UserProfileFactory, factory_related_name="user")
    token = factory.RelatedFactory(TokenFactory, factory_related_name="user")


class ContributorUserFactory(UserFactory):
    @factory.post_generation
    def add_to_contributors_group(self, create, extracted, **kwargs):
        if create:
            group, created = Group.objects.get_or_create(
                name=RNBContributorPermission.group_name
            )
            self.groups.add(group)
            self.save()
