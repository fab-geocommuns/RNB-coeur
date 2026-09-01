from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.management.commands.createsuperuser import (
    Command as BaseCreateSuperuserCommand,
)
from django.contrib.auth.models import Group
from django.db.models import Max

from batid.models import Organization, UserProfile


class Command(BaseCreateSuperuserCommand):
    """Extend the built-in createsuperuser to also add the new user to the
    Contributors group and give them a profile linked to the RNB team org."""

    def handle(self, *args, **options):
        User = get_user_model()
        max_pk_before = User.objects.aggregate(Max("pk"))["pk__max"] or 0

        super().handle(*args, **options)

        user = User.objects.filter(pk__gt=max_pk_before).latest("pk")

        group, _ = Group.objects.get_or_create(name=settings.CONTRIBUTORS_GROUP_NAME)
        user.groups.add(group)

        organization = Organization.objects.get(name=settings.RNB_TEAM_ORG_NAME)
        UserProfile.objects.get_or_create(
            user=user,
            defaults={"organization": organization, "job_title": "Admin"},
        )
