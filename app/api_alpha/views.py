from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.generics import ListCreateAPIView, ListAPIView
from rest_framework.views import APIView

from api_alpha.pagination import PagedNumberNoCount
from api_alpha.permissions import ADSPermission
from api_alpha.serializers import (
    ADSSerializer,
    BuildingSerializer,
    GuessBuildingSerializer,
    ContributionSerializer,
    BuildingClosestSerializer,
    BuildingClosestQuerySerializer,
)
from api_alpha.services import get_city_from_request
from batid.list_bdg import list_bdgs
from batid.services.closest_bdg import get_closest
from batid.services.rnb_id import clean_rnb_id
from batid.services.search_ads import ADSSearch
from batid.services.guess_bdg import BuildingGuess
from batid.models import ADS, Building, Contribution

from rest_framework import viewsets, status
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.response import Response

from django.http import HttpResponse, Http404
from batid.services.vector_tiles import tile_sql, url_params_to_tile
from rest_framework_tracking.mixins import LoggingMixin
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance


class RNBLoggingMixin(LoggingMixin):
    def should_log(self, request, response):
        return request.query_params.get("from") != "monitoring"


class BuildingGuessView(RNBLoggingMixin, APIView):
    def get(self, request, *args, **kwargs):
        search = BuildingGuess()
        search.set_params_from_url(**request.query_params.dict())

        qs = search.get_queryset()

        if not search.is_valid():
            return Response(
                {"errors": search.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = GuessBuildingSerializer(qs, many=True)

        return Response(serializer.data)


class BuildingClosestView(RNBLoggingMixin, APIView):
    def get(self, request, *args, **kwargs):
        query_serializer = BuildingClosestQuerySerializer(data=request.query_params)

        if query_serializer.is_valid():
            # todo : si ouverture du endpoint au public : ne permettre de voir que les bâtiments dont le statut est public et qui représente un bâtiment réel (cf `BuildingStatus.REAL_BUILDINGS_STATUS`)

            point = request.query_params.get("point")
            radius = request.query_params.get("radius")
            lat, lng = point.split(",")
            lat = float(lat)
            lng = float(lng)
            radius = int(radius)

            qs = get_closest(lat, lng, radius)
            bdg = qs.first()

            if isinstance(bdg, Building):
                serializer = BuildingClosestSerializer(bdg)
                return Response(serializer.data)
            else:
                return Response(
                    {"message": "No building found in the area"}, status=200
                )

        else:
            # Invalid data, return validation errors
            return Response(query_serializer.errors, status=400)


class BuildingCursorPagination(CursorPagination):
    page_size = 20
    ordering = "id"


class BuildingViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    lookup_field = "rnb_id"

    pagination_class = BuildingCursorPagination
    # pagination_class = PageNumberPagination

    def get_object(self):
        try:
            qs = list_bdgs({"user": self.request.user, "status": "all"})
            return qs.get(rnb_id=clean_rnb_id(self.kwargs["rnb_id"]))
        except Building.DoesNotExist:
            raise Http404

    def get_queryset(self):
        query_params = self.request.query_params.dict()
        query_params["user"] = self.request.user

        qs = list_bdgs(query_params)

        return qs


class ADSBatchViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "file_number"
    pagination_class = PageNumberPagination
    permission_classes = [ADSPermission]
    http_method_names = ["post"]

    max_batch_size = 30

    def create(self, request, *args, **kwargs):
        to_save = []
        errors = {}

        self.validate_length(request.data)

        for ads in request.data:
            try:
                instance = ADS.objects.get(file_number=ads["file_number"])
                serializer = self.get_serializer(instance, data=ads)
            except ADS.DoesNotExist:
                serializer = self.get_serializer(data=ads)

            if serializer.is_valid():
                city = get_city_from_request(ads, request.user, self)

                to_save.append({"city": city, "serializer": serializer})

            else:
                errors[ads["file_number"]] = serializer.errors

        if len(errors) > 0:
            return Response(errors, status=400)
        else:
            to_show = []
            for item in to_save:
                item["serializer"].save(city=item["city"])
                to_show.append(item["serializer"].data)

            return Response(to_show)

    def validate_length(self, data):
        if len(data) > self.max_batch_size:
            raise ParseError(
                {"errors": f"Too many items in the request. Max: {self.max_batch_size}"}
            )

        if len(data) == 0:
            raise ParseError({"errors": "No data in the request."})


class ADSViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "file_number"
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
            city = get_city_from_request(request.data, request.user, self)
            serializer.save(city=city)

            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def retrieve(self, request, file_number=None):
        return super().retrieve(request, file_number)


def get_tile(request, x, y, z):
    tile_dict = url_params_to_tile(x, y, z)
    sql = tile_sql(tile_dict)

    with connection.cursor() as cursor:
        cursor.execute(sql)
        tile_file = cursor.fetchone()[0]

    return HttpResponse(tile_file, content_type="application/vnd.mapbox-vector-tile")


class ContributionsViewSet(viewsets.ModelViewSet):
    queryset = Contribution.objects.all()
    http_method_names = ["post"]
    serializer_class = ContributionSerializer
