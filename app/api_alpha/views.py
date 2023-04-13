from rest_framework import viewsets

from rest_framework.exceptions import ParseError
from batid.models import Building, ADS, BuildingADS
from api_alpha.serializers import (
    BuildingSerializer,
    ADSSerializer,
)
from batid.logic.bdg_search import BuildingSearch
from batid.logic.ads_search import ADSSearch
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from api_alpha.permissions import ADSPermission


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
            pass

        return search.get_queryset()


class ADSViewSet(viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "issue_number"
    pagination_class = PageNumberPagination
    permission_classes = [ADSPermission]
    http_method_names = ["get", "post", "put", "delete"]

    def get_queryset(self):
        search = ADSSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            pass

        return search.get_queryset()

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=400)

    def retrieve(self, request, issue_number=None):
        return super().retrieve(request, issue_number)
