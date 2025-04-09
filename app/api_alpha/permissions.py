import copy

from django.conf import settings
from django.contrib.auth.models import Group
from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

from batid.services.ads import can_manage_ads


class ADSPermission(permissions.DjangoModelPermissions):
    """Custom permission class to allow access to ADS API."""

    def __init__(self):
        # Enforce 'view' permission for all GET requests (allowed by default in DjangoModelPermissions)
        self.perms_map = copy.deepcopy(self.perms_map)
        self.perms_map["GET"] = ["%(app_label)s.view_%(model_name)s"]

    def has_permission(self, request, view):

        # Everybody can list and retrieve ADS
        if view.action in ["list", "retrieve"]:
            return True

        # For others actions, we need to be authenticated and have the rights
        return request.user.is_authenticated and super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):

        # You are superuser? Please, be our guest
        # Superuser -> all permissions
        if request.user.is_authenticated and request.user.is_superuser:
            return True

        # Everybody can read ADS
        if view.action in ["retrieve"]:
            return True

        # For others actions, we need to be authenticated and have the rights
        # Not authenticated users -> no permission
        if not request.user.is_authenticated:
            return False

        # User does not have permission to perform this action (DjangoModelPermissions) -> no permission
        if not super().has_object_permission(request, view, obj):
            return False

        # ########
        # UPDATE
        if view.action == "update":

            # ##
            # We both have to check the right on the ADS before update and on the sent data

            # On the ADS
            if not can_manage_ads(request.user, obj):
                return False

            # On the request data
            # if not can_manage_ads_in_request(request.user, request.data):
            #     return False

            return True

        # ########
        # DESTROY
        if view.action == "destroy":
            return can_manage_ads(request.user, obj)

        # ########
        # READ
        if view.action == "retrieve":
            # Anybody authenticated user can read ADS
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


def is_in_group(user, group_name):
    try:
        return Group.objects.get(name=group_name).user_set.filter(id=user.id).exists()
    except Group.DoesNotExist:
        return False


class RNBContributorPermission(permissions.BasePermission):
    group_name = settings.CONTRIBUTORS_GROUP_NAME

    def has_permission(self, request, view):
        return is_in_group(request.user, self.group_name)


class ReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
