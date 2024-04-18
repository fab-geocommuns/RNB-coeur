from django.contrib.auth.models import User
from rest_framework import permissions

from api_alpha.services import calc_ads_cities
from batid.models import ADS
from batid.services.ads import manage_ads_in_cities
from batid.services.models_gears import UserGear


# We have to create a specific permission class for city validation
# It is executed after the ADSPermission class AND after the verification of the ADSSerializer.is_valid()
# We do so because we need some field of the request to calculate the permission.
# We prefer those fields to be validated before we use them.


class ADSCityPermission:
    def user_has_permission(self, city, user, view):
        if user.is_superuser:
            return True

        # We verify cities only in create and update views
        if view.action not in ["create", "update"]:
            return True

        if not user_can_manage_insee_code(user, city.code_insee):
            return False

        return True


class ADSPermission(permissions.BasePermission):
    """Custom permission class to allow access to ADS API."""

    def has_permission(self, request, view):

        print("######### has_permission #########")
        print("--- request")
        print(request)
        print("--- view")
        print(view)

        # You must best authenticated to do anything with an ADS
        if request.user.is_authenticated:


            if view.action == "create":

                cities = calc_ads_cities(request.data)
                return manage_ads_in_cities(request.user, cities)

            else:

                return True

        else:
            return False

    def has_object_permission(self, request, view, obj):

        print("######### has_object_permission #########")
        print("--- request")
        print(request)
        print("--- view")
        print(view)
        print("--- obj")
        print(obj)

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
    user = UserGear(user)
    return insee_code in user.get_managed_insee_codes()

def user_can_manage_city()