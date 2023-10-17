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
)
from api_alpha.services import get_city_from_request
from batid.list_bdg import public_bdg_queryset, filter_bdg_queryset
from batid.services.rnb_id import clean_rnb_id
from batid.services.search_ads import ADSSearch
from batid.services.search_bdg import BuildingGuess
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.models import ADS, Building

from rest_framework import viewsets, status
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from django.http import HttpResponse, Http404
from batid.services.vector_tiles import tile_sql, url_params_to_tile
from rest_framework_tracking.mixins import LoggingMixin


class BuildingGuessView(APIView):
    def get(self, request, *args, **kwargs):
        search = BuildingGuess()
        search.set_params(**request.query_params.dict())

        qs = search.get_queryset()

        if not search.is_valid():
            return Response(
                {"errors": search.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = GuessBuildingSerializer(qs, many=True)

        return Response(serializer.data)


class BuildingViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    lookup_field = "rnb_id"
    page_size = 20

    pagination_class = None

    def get_object(self):
        try:
            return Building.objects.get(rnb_id=clean_rnb_id(self.kwargs["rnb_id"]))
        except Building.DoesNotExist:
            raise Http404

    def get_queryset(self):
        qs = public_bdg_queryset(self.request.user)
        qs = filter_bdg_queryset(qs, self.request.query_params)

        # Paginate the queryset
        page = self.request.query_params.get("page", 1)
        start = (int(page) - 1) * self.page_size
        end = start + self.page_size

        return qs[start:end]


class ADSBatchViewSet(LoggingMixin, viewsets.ModelViewSet):
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


class ADSViewSet(LoggingMixin, viewsets.ModelViewSet):
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
