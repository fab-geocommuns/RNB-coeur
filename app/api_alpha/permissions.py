from rest_framework import permissions
from api_alpha.services import calc_ads_request_cities, can_manage_ads_in_request
from batid.services.ads import can_manage_ads_in_cities, can_manage_ads


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
            return can_manage_ads_in_request(request.user, request.data)

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
            return can_manage_ads_in_request(request.user, request.data)

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
