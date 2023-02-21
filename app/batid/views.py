from django.shortcuts import render
from rest_framework import viewsets
from batid.models import Building
from batid.serializers import BuildingSerializer

class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
