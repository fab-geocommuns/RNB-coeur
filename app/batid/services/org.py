from batid.models import Organization
from batid.models import UserProfile


def populate_organization_on_profiles():
    for org in Organization.objects.prefetch_related("users").order_by("pk"):
        for user in org.users.all():
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.organization_id is None:
                profile.organization = org
                profile.save(update_fields=["organization"])
