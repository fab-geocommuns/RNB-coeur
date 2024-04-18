from django.contrib.auth.models import User
from rest_framework import permissions

from api_alpha.services import calc_ads_request_cities
from batid.models import ADS
from batid.services.ads import can_manage_ads_in_cities


class ADSPermission(permissions.BasePermission):
    """Custom permission class to allow access to ADS API."""

    def has_permission(self, request, view):

        # Not authenticated users -> no permission
        if not request.user.is_authenticated:
            return False

        # Super user -> all permissions
        if request.user.is_authenticated and request.user.is_superuser:
            return True

        if view.action == "create":

            cities = calc_ads_request_cities(request.data)
            return can_manage_ads_in_cities(request.user, cities)

        return True

    def has_object_permission(self, request, view, obj):

        # print("######### has_object_permission #########")
        # print("--- request")
        # print(request)
        # print("--- view")
        # print(view)
        # print("--- obj")
        # print(obj)

        # Not authenticated users -> no permission
        if not request.user.is_authenticated:
            return False

        # Super user -> all permissions
        if request.user.is_authenticated and request.user.is_superuser:
            return True

        if view.action == "update":

            # ##
            # We both have to check the right on the ADS before update and on the sent data

            # On the ADS
            if not user_can_manage_ads(request.user, obj):
                return False

            # On the data
            cities = calc_ads_request_cities(request.data)
            sent_data_are_ok = can_manage_ads_in_cities(request.user, cities)
            if not sent_data_are_ok:
                return False

        if view.action in ["update", "destroy"]:

            return user_can_manage_ads(request.user, obj)

        # Anybody can read ADS
        if view.action in ["retrieve"]:
            return True

        raise NotImplementedError(f"Unknown action {view.action}")


# def get_city_from_request(data, user, view):
#     cities = calc_ads_cities(data)
#
#     # First we validate we have only one city
#
#     if len(cities) == 0:
#         raise serializers.ValidationError(
#             {"buildings_operations": ["Buildings are in an unknown city"]}
#         )
#
#     if len(cities) > 1:
#         raise serializers.ValidationError(
#             {"buildings_operations": ["Buildings must be in only one city"]}
#         )
#
#     city = cities[0]
#
#     # Then we do permission
#
#     perm = ADSCityPermission()
#
#     if not perm.user_has_permission(city, user, view):
#         raise exceptions.PermissionDenied(detail="You can not edit ADS in this city.")
#
#     return city
