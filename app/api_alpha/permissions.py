from rest_framework import permissions
from django.contrib.auth.models import User
from batid.models import ADS
from batid.logic.user import RNBUser


class ADSPermission(permissions.BasePermission):
    """Custom permission class to allow access to ADS API."""

    def has_permission(self, request, view):
        if view.action in ["create", "update"]:
            if request.user.is_superuser:
                return True

            if request.data.get("insee_code"):
                return user_can_manage_insee_code(
                    request.user, request.data["insee_code"]
                )

            # we don't have enough information (the insee_code) to decide
            return True

        else:
            return True

    def has_object_permission(self, request, view, obj):
        if view.action in ["create", "update", "destroy"]:
            if not request.user.is_authenticated:
                return False

            if request.user.is_authenticated and request.user.is_superuser:
                return True

            return user_can_manage_ads(request.user, obj)

        # Anybody can read ADS
        if view.action in ["retrieve"]:
            return True

        raise NotImplementedError(f"Unknown action {view.action}")


def user_can_manage_ads(user: User, ads: ADS) -> bool:
    return user_can_manage_insee_code(user, ads.insee_code)


def user_can_manage_insee_code(user: User, insee_code: str) -> bool:
    user = RNBUser(user)
    return insee_code in user.get_managed_insee_codes()
