from django.shortcuts import render
from rest_framework import viewsets
from batid.models import Building
from batid.serializers import BuildingSerializer
from rest_framework.pagination import PageNumberPagination

class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ['get']
    pagination_class = PageNumberPagination
