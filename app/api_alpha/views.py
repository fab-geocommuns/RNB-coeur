from api_alpha.serializers import BuildingSerializer, CitySerializer
from batid.logic.search import BuildingSearch
from batid.models import Building, City
from django.db.models import Q
from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ReadOnlyModelViewSet


class BuildingViewSet(ReadOnlyModelViewSet):
    def get_queryset(self):
        search = BuildingSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            pass

        return search.get_queryset()

    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    pagination_class = PageNumberPagination


class CityViewSet(ReadOnlyModelViewSet):
    """View to look up city matching (name or postal code) with a given input"""

    queryset = City.objects.all()

    def get_queryset(self):
        query = self.request.query_params.dict()
        print(query)
        queryset = City.objects.filter(
            Q(name__unaccent__icontains=query["txt"])
            | Q(code_insee__icontains=query["txt"])
        )
        return queryset

    serializer_class = CitySerializer
    http_method_names = ["get"]
    # pagination_class = PageNumberPagination
