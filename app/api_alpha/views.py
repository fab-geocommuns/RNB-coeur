from api_alpha.permissions import ADSPermission, ADSCityPermission
from api_alpha.serializers import ADSSerializer, BuildingSerializer
from batid.services.search_ads import ADSSearch
from batid.services.search_bdg import BuildingSearch
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.models import ADS, Building, BuildingADS

from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from batid.services.rnb_id import clean_rnb_id


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    pagination_class = PageNumberPagination
    lookup_field = "rnb_id"

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
            "Expected view %s to be called with a URL keyword argument "
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            "attribute on the view correctly."
            % (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: clean_rnb_id(self.kwargs[lookup_url_kwarg])}

        obj = get_object_or_404(queryset, **filter_kwargs)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj

    def get_queryset(self):
        search = BuildingSearch()

        # If the user is authenticated, it has access to the full list of status
        if self.request.user.is_authenticated:
            search.params.allowed_status = BuildingStatusModel.ALL_TYPES_KEYS

        # If we are listing buildings, the default status we display are those ones
        if self.action == "list":
            search.params.status = [
                "ongoingConstruction",
                "constructed",
                "ongoingChange",
                "notUsable",
            ]

        # Then we apply the filters requested by the user
        search.set_params(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            return

        return search.get_queryset()


class ADSViewSet(viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "file_number"
    pagination_class = PageNumberPagination
    permission_classes = [ADSPermission]
    http_method_names = ["get", "post", "put", "delete"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_cities = []

    def get_queryset(self):
        search = ADSSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            pass

        return search.get_queryset()

    def check_request_cities_permissions(self, request):
        # The pattern is quite the same as the check_permissions() method of the APIView class

        permission = ADSCityPermission()

        has_permission = permission.has_permission(request, self)
        # We capture the calculation of the cities so we dont have to do it again to attach the city in the serializer
        self.request_cities = permission.request_cities

        if not has_permission:
            self.permission_denied(
                request,
                message=getattr(permission, "message", None),
                code=getattr(permission, "code", None),
            )

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.check_request_cities_permissions(request)
            serializer.install_cities(self.request_cities)

            if serializer.has_valid_cities():
                self.perform_create(serializer)
                return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def retrieve(self, request, file_number=None):
        return super().retrieve(request, file_number)
