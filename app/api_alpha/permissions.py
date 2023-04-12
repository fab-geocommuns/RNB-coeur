from rest_framework import permissions
from django.contrib.auth.models import User
from batid.models import ADS
from batid.logic.user import RNBUser


class ADSPermission(permissions.BasePermission):
    """Custom permission class to allow access to ADS API."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_authenticated and request.user.is_superuser:
            return True

        if view.action in ["create", "update", "destroy"]:
            return user_can_manage_ads(request.user, obj)

        return True


def user_can_manage_ads(user: User, ads: ADS) -> bool:
    user = RNBUser(user)
    return ads.insee_code in user.get_managed_insee_codes()
