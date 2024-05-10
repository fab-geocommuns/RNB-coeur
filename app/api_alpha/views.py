from base64 import b64encode

import requests
from django.db import connection
from django.http import Http404
from django.http import HttpResponse
from drf_spectacular.openapi import OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.pagination import BasePagination
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView
from rest_framework_tracking.mixins import LoggingMixin
from rest_framework_tracking.models import APIRequestLog

from api_alpha.permissions import ADSPermission
from api_alpha.serializers import ADSSerializer
from api_alpha.serializers import BuildingClosestQuerySerializer
from api_alpha.serializers import BuildingClosestSerializer
from api_alpha.serializers import BuildingSerializer
from api_alpha.serializers import ContributionSerializer
from api_alpha.serializers import GuessBuildingSerializer
from batid.list_bdg import list_bdgs
from batid.models import ADS
from batid.models import Building
from batid.models import Contribution
from batid.services.closest_bdg import get_closest
from batid.services.guess_bdg import BuildingGuess
from batid.services.rnb_id import clean_rnb_id
from batid.services.search_ads import ADSSearch
from batid.services.vector_tiles import tile_sql
from batid.services.vector_tiles import url_params_to_tile


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


class BuildingCursorPagination(BasePagination):
    page_size = 20

    cursor_query_param = "cursor"

    def __init__(self):
        self.base_url = None
        self.current_page = None

        self.has_next = False
        self.has_previous = False

        self.page = None

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "next": {
                    "type": "string",
                    "nullable": True,
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                },
                "results": schema,
            },
        }

    def get_html_context(self):
        return {
            "previous_url": self.get_previous_link(),
            "next_url": self.get_next_link(),
        }

    def get_paginated_response(self, data):

        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_next_link(self):

        if self.has_next:
            next_cursor = str(self.current_page + 1)
            return replace_query_param(
                self.base_url, self.cursor_query_param, next_cursor
            )

        return None

    def get_previous_link(self):

        if self.has_previous:
            previous_cursor = str(self.current_page - 1)
            return replace_query_param(
                self.base_url, self.cursor_query_param, previous_cursor
            )

        return None

    def paginate_queryset(self, queryset, request, view=None):

        # Get the current URL with all parameters
        self.base_url = request.build_absolute_uri()

        self.current_page = self.get_page(request)
        if self.current_page is None:
            self.current_page = 1

        offset = (self.current_page - 1) * self.page_size

        # If we have an offset cursor then offset the entire page by that amount.
        # We also always fetch an extra item in order to determine if there is a
        # page following on from this one.
        results = queryset[offset : offset + self.page_size + 1]

        if len(results) > self.page_size:
            self.has_next = True

        if self.current_page > 1:
            self.has_previous = True

        return results[: self.page_size]

    def get_page(self, request):

        request_page = request.query_params.get(self.cursor_query_param)
        if request_page:
            try:
                return int(request_page)
            except ValueError:
                return None

        return None

    def encode_cursor(self, cursor):

        return b64encode(cursor.encode("ascii")).decode("ascii")


class BuildingViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = Building.objects.all().filter(is_active=True)
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "bb",
                str,
                OpenApiParameter.QUERY,
                description="""
                    Filtre les bâtiments grâce à une bounding box.

                    Le format est nw_lat,nw_lng,se_lat,se_lng avec :

                    • nw_lat : latitude du point Nord Ouest
                    • nw_lng : longitude du point Nord Ouest
                    • se_lat : latitude du point Sud Est
                    • se_lng : longitude du point Sud Est
                """,
                examples=[
                    OpenApiExample(
                        "Exemple 1", value="48.845782,2.424525,48.839201,2.434158"
                    )
                ],
            ),
            OpenApiParameter(
                "status",
                str,
                OpenApiParameter.QUERY,
                enum=[
                    "constructed",
                    "ongoingChange",
                    "notUsable",
                    "demolished",
                    "constructionProject",
                    "canceledConstructionProject",
                ],
                description="""
                    Filtre les bâtiments par statut.

                    • constructed : Bâtiment construit
                    • ongoingChange : En cours de modification
                    • notUsable : Non utilisable (ex : une ruine)
                    • demolished : Démoli

                    Statuts réservés aux instructeurs d’autorisation du droit des sols.

                    • constructionProject : Bâtiment en projet
                    • canceledConstructionProject : Projet de bâtiment annulé
                """,
                examples=[
                    OpenApiExample(
                        "Exemple 1",
                        summary="Liste les bâtiments construits",
                        value="constructed",
                    ),
                    OpenApiExample(
                        "Exemple 2",
                        summary="Liste les bâtiments construits ou démolis",
                        value="constructed,demolished",
                    ),
                ],
            ),
            OpenApiParameter(
                "insee_code",
                str,
                OpenApiParameter.QUERY,
                description="""
                    Filtre les bâtiments grâce au code INSEE d'une commune.
                     """,
                examples=[
                    OpenApiExample(
                        "Liste les bâtiments de la commune de Talence", value="33522"
                    )
                ],
            ),
        ],
        examples=[
            OpenApiExample(
                "Exemple 1",
                summary="Liste les bâtiments de la commune de Talence",
                value="GET https://rnb-api.beta.gouv.fr/api/alpha/buildings/?insee_code=33522",
            ),
            OpenApiExample(
                "Exemple 2",
                summary="Liste les bâtiments construits ou démolis",
                value="GET https://rnb-api.beta.gouv.fr/api/alpha/buildings/?status=constructed,demolished",
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """
        Renvoie une liste paginée de bâtiments. Des filtres (notamment par code INSEE de la commune) sont disponibles.
        """
        return super().list(request, *args, **kwargs)


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
                to_save.append({"serializer": serializer})

            else:
                errors[ads["file_number"]] = serializer.errors

        if len(errors) > 0:
            return Response(errors, status=400)
        else:
            to_show = []
            for item in to_save:
                item["serializer"].save()
                to_show.append(item["serializer"].data)

            return Response(to_show, status=201)

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

        return search.get_queryset()


def get_tile(request, x, y, z):
    # Check the request zoom level
    if int(z) >= 16:
        tile_dict = url_params_to_tile(x, y, z)
        sql = tile_sql(tile_dict)

        with connection.cursor() as cursor:
            cursor.execute(sql)
            tile_file = cursor.fetchone()[0]

        return HttpResponse(
            tile_file, content_type="application/vnd.mapbox-vector-tile"
        )
    else:
        return HttpResponse(status=204)


def get_data_gouv_publication_count():
    # call data.gouv.fr API to get the number of datasets
    req = requests.get("https://www.data.gouv.fr/api/1/datasets/?tag=rnb")
    if req.status_code != 200:
        return None
    else:
        # remove the dataset that is the RNB
        return req.json()["total"] - 1


def get_stats(request):
    def get_building_count_estimate():
        cursor = connection.cursor()
        # fast way to get an estimate
        cursor.execute(
            "SELECT reltuples::bigint FROM pg_class WHERE relname='batid_building'"
        )
        return cursor.fetchone()[0]

    building_counts = get_building_count_estimate()
    api_calls_since_2024_count = APIRequestLog.objects.filter(
        requested_at__gte="2024-01-01T00:00:00Z"
    ).count()
    contributions_count = Contribution.objects.count()
    data_gouv_publication_count = get_data_gouv_publication_count()

    data = {
        "building_counts": building_counts,
        "api_calls_since_2024_count": api_calls_since_2024_count,
        "contributions_count": contributions_count,
        "data_gouv_publication_count": data_gouv_publication_count,
    }

    renderer = JSONRenderer()
    response = HttpResponse(renderer.render(data), content_type="application/json")

    return response


class ContributionsViewSet(viewsets.ModelViewSet):
    queryset = Contribution.objects.all()
    http_method_names = ["post"]
    serializer_class = ContributionSerializer
