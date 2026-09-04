import factory
from api_alpha.permissions import (
    RNBContributorPermission,
    RNBReviewerPermission,
    RollbackPermission,
)
from batid.models import UserProfile
from django.contrib.auth.models import Group, User
from rest_framework.authtoken.models import Token


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
    def add_to_contributors_group(self, create, _extracted, **kwargs):
        if create:
            group, created = Group.objects.get_or_create(
                name=RNBContributorPermission.group_name
            )
            self.groups.add(group)
            self.save()


class ReviewerUserFactory(UserFactory):
    @factory.post_generation
    def add_to_reviewers_group(self, create, _extracted, **kwargs):
        if create:
            group, created = Group.objects.get_or_create(
                name=RNBReviewerPermission.group_name
            )
            self.groups.add(group)
            self.save()


class RollbackUserFactory(UserFactory):
    """Staff user member of the Rollback group: can call the rollback endpoint.

    Distinct from ReviewerUserFactory: seeing the rollback button in the UI only
    requires being a Reviewer, but actually performing a rollback requires this.
    """

    is_staff = True

    @factory.post_generation
    def add_to_rollback_group(self, create, _extracted, **kwargs):
        if create:
            group, created = Group.objects.get_or_create(
                name=RollbackPermission.group_name
            )
            self.groups.add(group)
            self.save()
