from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.exceptions import ParseError
from batid.models import Building
from batid.serializers import BuildingSerializer
from batid.logic.search import BuildingSearch
from rest_framework.pagination import PageNumberPagination

class BuildingViewSet(ReadOnlyModelViewSet):

    def get_queryset(self):

        search = BuildingSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({'errors': search.errors})
            pass

        return search.get_queryset()

    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ['get']
    pagination_class = PageNumberPagination
