from django.db import connection

from api_alpha.permissions import ADSPermission
from api_alpha.serializers import ADSSerializer, BuildingSerializer
from api_alpha.services import get_city_from_request
from batid.services.search_ads import ADSSearch
from batid.services.search_bdg import BuildingSearch
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.models import ADS, Building

from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from django.http import HttpResponse, Http404
from batid.services.vector_tiles import tile_sql, url_params_to_tile


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    lookup_field = "rnb_id"

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        search = BuildingSearch()

        search.set_params_from_url(**{"rnb_id": self.kwargs[lookup_url_kwarg]})

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            return

        qs = search.get_queryset()

        if len(qs) == 0:
            raise Http404
            return

        obj = qs[0]

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
        search.set_params_from_url(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            return

        return search.get_queryset()


class ADSBatchViewSet(viewsets.ModelViewSet):
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


class ADSViewSet(viewsets.ModelViewSet):
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
