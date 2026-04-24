# populate_organization_on_profiles was a one-time helper that populated
# UserProfile.organization from the Organization.users M2M relation.
# The M2M was removed when migrating from N:N to 1:N user-org membership
# (migration 0129). The function is kept here for reference only.
# from batid.models import Organization, UserProfile
#
#
# def populate_organization_on_profiles():
#     for org in Organization.objects.prefetch_related("users").order_by("pk"):
#         for user in org.users.all():
#             profile, _ = UserProfile.objects.get_or_create(user=user)
#             if profile.organization_id is None:
#                 profile.organization = org
#                 profile.save(update_fields=["organization"])
