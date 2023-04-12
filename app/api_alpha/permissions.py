from rest_framework import permissions
from django.contrib.auth.models import User
from batid.models import ADS
from batid.logic.user import RNBUser


class ADSPermission(permissions.BasePermission):
    """Custom permission class to allow access to ADS API."""

    def has_permission(self, request, view):
        if view.action in ["create", "update"]:
            if not request.user.is_authenticated:
                return False

            if request.user.is_superuser:
                return True

            return user_can_manage_insee_code(request.user, request.data["insee_code"])

        else:
            return True

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if request.user.is_authenticated and request.user.is_superuser:
            return True

        if view.action in ["create", "update", "destroy"]:
            return user_can_manage_ads(request.user, obj)

        raise NotImplementedError(f"Unknown action {view.action}")


def user_can_manage_ads(user: User, ads: ADS) -> bool:
    return user_can_manage_insee_code(user, ads.insee_code)


def user_can_manage_insee_code(user: User, insee_code: str) -> bool:
    user = RNBUser(user)
    return insee_code in user.get_managed_insee_codes()
