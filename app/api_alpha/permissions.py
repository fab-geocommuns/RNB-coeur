from rest_framework import permissions
from django.contrib.auth.models import User
from batid.models import ADS
from batid.services.user import RNBUser
from api_alpha.services import calc_ads_cities


# We have to create a specific permission class for city validation
# It is executed after the ADSPermission class AND after the verification of the ADSSerializer.is_valid()
# We do so because we need some field of the request to calculate the permission.
# We prefer those fields to be validated before we use them.
class ADSCityPermission(permissions.BasePermission):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_cities = []

    def has_permission(self, request, view):
        if view.action in ["create", "update"]:
            # We have to calculate anyway since we will need the cities later
            self.request_cities = calc_ads_cities(request.data)

            if request.user.is_superuser:
                return True

            # should it be here we validate they can only request one city at a time ?
            # It might be in a validator of the serializer
            # if len(self.request_cities) != 1:
            #     return False

            for city in self.request_cities:
                if not user_can_manage_insee_code(request.user, city.code_insee):
                    return False

            return True

        else:
            return True


class ADSPermission(permissions.BasePermission):
    """Custom permission class to allow access to ADS API."""

    def has_permission(self, request, view):
        # The permission is checked later in the process (in the ADSCityPermission class)
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
    return user_can_manage_insee_code(user, ads.city.code_insee)


def user_can_manage_insee_code(user: User, insee_code: str) -> bool:
    user = RNBUser(user)
    return insee_code in user.get_managed_insee_codes()
