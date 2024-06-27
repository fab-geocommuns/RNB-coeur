import copy

from rest_framework import permissions

from batid.services.ads import can_manage_ads


class ADSPermission(permissions.DjangoModelPermissions):
    """Custom permission class to allow access to ADS API."""

    def __init__(self):
        # Enforce 'view' permission for all GET requests (allowed by default in DjangoModelPermissions)
        self.perms_map = copy.deepcopy(self.perms_map)
        self.perms_map["GET"] = ["%(app_label)s.view_%(model_name)s"]

    def has_permission(self, request, view):

        return request.user.is_authenticated and super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):

        # Not authenticated users -> no permission
        if not request.user.is_authenticated:
            return False

        # Super user -> all permissions
        if request.user.is_authenticated and request.user.is_superuser:
            return True

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
