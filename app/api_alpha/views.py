from api_alpha.permissions import ADSPermission, ADSCityPermission
from api_alpha.serializers import ADSSerializer, BuildingSerializer
from api_alpha.logic import calc_ads_cities
from batid.logic.ads_search import ADSSearch
from batid.logic.bdg_search import BuildingSearch
from batid.models import ADS, Building, BuildingADS
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    pagination_class = PageNumberPagination
    lookup_field = "rnb_id"

    def get_queryset(self):
        search = BuildingSearch(**self.request.query_params.dict())

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
