import json
import os
from base64 import b64encode
from datetime import datetime

import requests
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.db import connection
from django.db import transaction
from django.http import HttpResponse
from django.http import JsonResponse
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse
from psycopg2 import sql
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError
from rest_framework.pagination import BasePagination
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
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
from api_alpha.utils.rnb_doc import build_schema_dict
from api_alpha.utils.rnb_doc import get_status_html_list
from api_alpha.utils.rnb_doc import rnb_doc
from batid.list_bdg import list_bdgs
from batid.models import ADS
from batid.models import Building
from batid.models import Contribution
from batid.models import Organization
from batid.services.closest_bdg import get_closest_from_point
from batid.services.guess_bdg import BuildingGuess
from batid.services.rnb_id import clean_rnb_id
from batid.services.search_ads import ADSSearch
from batid.services.vector_tiles import ads_tiles_sql
from batid.services.vector_tiles import bdgs_tiles_sql
from batid.services.vector_tiles import url_params_to_tile
from batid.utils.constants import ADS_GROUP_NAME


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class RNBLoggingMixin(LoggingMixin):
    def should_log(self, request, response):
        return request.query_params.get("from") != "monitoring"


class BuildingGuessView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Identification de bâtiment",
                "description": (
                    "Ce endpoint permet d'identifier le bâtiment correspondant à une série de critères. Il permet d'accueillir des données imprécises et tente de les combiner pour fournir le meilleur résultat. NB : l'URL se termine nécessairement par un slash (/)."
                ),
                "operationId": "guessBuilding",
                "parameters": [
                    {
                        "name": "address",
                        "in": "query",
                        "description": "Adresse du bâtiment",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "1 rue de la paix, Mérignac",
                    },
                    {
                        "name": "point",
                        "in": "query",
                        "description": "Coordonnées GPS du bâtiment. Format : <code>lat,lng</code>.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "44.84114313595151,-0.5705289444867035",
                    },
                    {
                        "name": "name",
                        "in": "query",
                        "description": "Nom du bâtiment. Est transmis à un géocoder OSM (<a href='https://github.com/komoot/photon'>Photon</a>).",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "Notre Dame de Paris",
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "description": "Numéro de page pour la pagination",
                        "required": False,
                        "schema": {"type": "integer"},
                        "example": 1,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste des bâtiments identifiés triés par score descendant.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "items": {
                                        "allOf": [
                                            {"$ref": "#/components/schemas/Building"},
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "score": {
                                                        "type": "number",
                                                        "description": "Score de correspondance entre la requête et le bâtiment",
                                                        "example": 0.8,
                                                    },
                                                    "sub_scores": {
                                                        "type": "object",
                                                        "description": "Liste des scores intermédiaires. Leur somme est égale au score principal.",
                                                    },
                                                },
                                            },
                                        ]
                                    },
                                    "type": "array",
                                }
                            }
                        },
                    }
                },
            }
        }
    )
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


@extend_schema(exclude=True)
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

            qs = get_closest_from_point(lat, lng, radius)
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
        qs = list_bdgs({"user": self.request.user, "status": "all"}, only_active=False)
        return get_object_or_404(qs, rnb_id=clean_rnb_id(self.kwargs["rnb_id"]))

    def get_queryset(self):
        query_params = self.request.query_params.dict()
        query_params["user"] = self.request.user

        qs = list_bdgs(query_params)

        return qs

    @rnb_doc(
        {
            "get": {
                "summary": "Liste des batiments",
                "description": (
                    "Ce endpoint permet de récupérer une liste paginée de bâtiments. "
                    "Des filtres, notamment par code INSEE de la commune, sont disponibles. NB : l'URL se termine nécessairement par un slash (/)."
                ),
                "operationId": "listBuildings",
                "parameters": [
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": "Filtre les bâtiments dont l'emprise au sol est située dans les limites géographiques de la commune ayant ce code INSEE.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75101",
                    },
                    {
                        "name": "status",
                        "in": "query",
                        "description": f"Filtre les bâtiments par statut. Il est possible d'utiliser plusieurs valeurs séparées par des virgules. Les valeurs possibles sont : <br /><br /> {get_status_html_list()}<br />",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "constructed,demolished",
                    },
                    {
                        "name": "cle_interop_ban",
                        "in": "query",
                        "description": "Filtre les bâtiments associés à cette clé d'interopérabilité BAN.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "94067_7115_00073",
                    },
                    {
                        "name": "bb",
                        "in": "query",
                        "description": (
                            "Filtre les bâtiments dont l'emprise au sol est située dans la bounding box"
                            "définie par les coordonnées Nord-Ouest et Sud-Est. Les coordonnées sont séparées par des virgules. "
                            "Le format est <code>nw_lat,nw_lng,se_lat,se_lng</code> où : <br/>"
                            "<ul>"
                            "<li><b>nw_lat</b> : latitude du point Nord Ouest de la bounding box</li>"
                            "<li><b>nw_lng</b> : longitude du point Nord Ouest de la bounding box</li>"
                            "<li><b>se_lat</b> : latitude du point Sud Est de la bounding box</li>"
                            "<li><b>se_lng</b> : longitude du point Sud Est de la bounding box</li>"
                            "</ul><br />"
                        ),
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "48.845782,2.424525,48.839201,2.434158",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée de bâtiments",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "<br />URL de la page de résultats suivante<br />",
                                            "nullable": True,
                                            "example": f"{settings.URL}/api/alpha/buildings/?cursor=cD02MzQ3OTk1",
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "<br />URL de la page de résultats précédente<br />",
                                            "nullable": True,
                                            "example": f"{settings.URL}/api/alpha/buildings/?cursor=hFG78YEdFR",
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/Building",
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            },
        },
    )
    def list(self, request, *args, **kwargs):
        """
        Renvoie une liste paginée de bâtiments. Des filtres (notamment par code INSEE de la commune) sont disponibles.
        """
        return super().list(request, *args, **kwargs)

    @rnb_doc(
        {
            "get": {
                "summary": "Consultation d'un bâtiment",
                "description": "Ce endpoint permet de récupérer l'ensemble des attributs d'un bâtiment à partir de son identifiant RNB. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "getBuilding",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/Building",
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def retrieve(self, request, *args, **kwargs):
        """
        Renvoie les détails d'un bâtiment spécifique identifié par son RNB ID.
        """
        return super().retrieve(request, *args, **kwargs)


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

    @extend_schema(
        tags=["ADS"],
        operation_id="list_ads",
        summary="Liste et recherche d'ADS",
        description=(
            "Cette API permet de lister et de rechercher des ADS (Autorisation de Droit de Sol). "
            "Les requêtes doivent être authentifiées en utilisant un token. "
            "Les filtres de recherche peuvent être passés en tant que paramètres d'URL."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                description="Recherche parmi les n° de dossiers (file_number).",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="since",
                description="Récupère tous les dossiers décidés depuis cette date (AAAA-MM-DD).",
                required=False,
                type=str,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "count": 3,
                            "next": None,
                            "previous": None,
                            "results": [
                                {
                                    "file_number": "TEST03818519U9999",
                                    "decided_at": "2023-06-01",
                                    "buildings_operations": [
                                        {
                                            "rnb_id": "A1B2C3A1B2C3",
                                            "shape": None,
                                            "operation": "build",
                                        },
                                        {
                                            "rnb_id": None,
                                            "shape": {
                                                "type": "Point",
                                                "coordinates": [
                                                    5.722961565015281,
                                                    45.1851103238598,
                                                ],
                                            },
                                            "operation": "demolish",
                                        },
                                        {
                                            "rnb_id": "1M2N3O1M2N3O",
                                            "shape": {
                                                "type": "Point",
                                                "coordinates": [
                                                    5.723006573148693,
                                                    45.1851402293713,
                                                ],
                                            },
                                            "operation": "demolish",
                                        },
                                    ],
                                },
                                {
                                    "file_number": "PC3807123200WW",
                                    "decided_at": "2023-05-01",
                                    "buildings_operations": [
                                        {
                                            "rnb_id": "FXFJZNZYGTED",
                                            "shape": None,
                                            "operation": "build",
                                        }
                                    ],
                                },
                                {
                                    "file_number": "PC384712301337",
                                    "decided_at": "2023-02-22",
                                    "buildings_operations": [
                                        {
                                            "rnb_id": "RXNOSN2DUCLG",
                                            "geometry": {
                                                "type": "Point",
                                                "coordinates": [
                                                    5.775791408470412,
                                                    45.256939624268206,
                                                ],
                                            },
                                            "operation": "modify",
                                        }
                                    ],
                                },
                            ],
                        },
                    )
                ],
            )
        },
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="get_ads",
        summary="Consultation d'une ADS",
        description=(
            "Cette API permet de récupérer une ADS (Autorisation de Droit de Sol). "
            "Les requêtes doivent être authentifiées en utilisant un token. "
        ),
        parameters=[
            OpenApiParameter(
                name="file_number",
                description="Récupération par n° de dossier (file_number).",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "file_number": "TEST03818519U9999",
                            "decided_at": "2023-06-01",
                            "buildings_operations": [
                                {
                                    "rnb_id": "A1B2C3A1B2C3",
                                    "shape": None,
                                    "operation": "build",
                                },
                                {
                                    "rnb_id": None,
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            5.722961565015281,
                                            45.1851103238598,
                                        ],
                                    },
                                    "operation": "demolish",
                                },
                                {
                                    "rnb_id": "1M2N3O1M2N3O",
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            5.723006573148693,
                                            45.1851402293713,
                                        ],
                                    },
                                    "operation": "demolish",
                                },
                            ],
                        },
                    )
                ],
            )
        },
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="create_ads",
        summary="Création d'une ADS",
        description=(
            "Ce endpoint permet de créer une Autorisation du Droit des Sols (ADS) dans le RNB. "
            "L'API ADS est réservée aux communes et requiert une authentification par token."
        ),
        request=ADSSerializer,
        responses={
            201: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "file_number": "PCXXXXXXXXXX",
                            "decided_at": "2019-03-18",
                            "buildings_operations": [
                                {
                                    "operation": "demolish",
                                    "rnb_id": "ABCD1234WXYZ",
                                    "shape": None,
                                },
                                {
                                    "operation": "build",
                                    "rnb_id": None,
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            2.3552747458487002,
                                            48.86958288638419,
                                        ],
                                    },
                                },
                            ],
                        },
                    )
                ],
            ),
            400: {"description": "Requête invalide"},
        },
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="update_ads",
        summary="Modification d'une ADS",
        description=(
            "Ce endpoint permet de modifier une Autorisation du Droit des Sols (ADS) existante dans le RNB. "
            "L'API ADS est réservée aux communes et requiert une authentification par token."
        ),
        request=ADSSerializer,
        responses={
            200: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "file_number": "PCXXXXXXXXXX",
                            "decided_at": "2019-03-10",
                            "buildings_operations": [
                                {
                                    "operation": "demolish",
                                    "rnb_id": "7865HG43PLS9",
                                    "shape": None,
                                },
                                {
                                    "operation": "build",
                                    "rnb_id": None,
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            2.3552747458487002,
                                            48.86958288638419,
                                        ],
                                    },
                                },
                            ],
                        },
                    )
                ],
            ),
            400: {"description": "Requête invalide"},
            404: {"description": "ADS non trouvée"},
        },
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="delete_ads",
        summary="Suppression d'une ADS",
        description="Ce endpoint permet de supprimer une Autorisation du Droit des Sols (ADS) existante dans le RNB.",
        responses={
            204: {"description": "ADS supprimée avec succès"},
            404: {"description": "ADS non trouvée"},
        },
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class ADSVectorTileView(APIView):
    def get(self, request, x, y, z):

        # might do : include a minimum zoom level as it is done for buildings
        tile_dict = url_params_to_tile(x, y, z)
        sql = ads_tiles_sql(tile_dict)

        with connection.cursor() as cursor:
            cursor.execute(sql)
            tile_file = cursor.fetchone()[0]

        return HttpResponse(
            tile_file, content_type="application/vnd.mapbox-vector-tile"
        )


class BuildingsVectorTileView(APIView):
    @extend_schema(
        tags=["Tile"],
        operation_id="get_vector_tile",
        summary="Obtenir une tuile vectorielle",
        description=(
            "Cette API fournit des tuiles vectorielles au format PBF permettant d'intégrer les bâtiments "
            "du Référentiel National des Bâtiments (RNB) dans une cartographie. Chaque tuile contient des points "
            "représentant des bâtiments avec un attribut 'rnb_id'. Les tuiles sont utilisables avec un niveau de zoom "
            "minimal de 16 et peuvent être intégrées dans des outils comme QGIS ou des sites web."
        ),
        auth=[],
        parameters=[
            OpenApiParameter(
                name="x",
                description="Coordonnée X de la tuile",
                required=True,
                type=int,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="y",
                description="Coordonnée Y de la tuile",
                required=True,
                type=int,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="z",
                description="Niveau de zoom de la tuile",
                required=True,
                type=int,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Fichier PBF contenant les tuiles vectorielles",
            ),
            400: {"description": "Requête invalide"},
        },
    )
    def get(self, request, x, y, z):
        # Check the request zoom level
        if int(z) >= 16:
            tile_dict = url_params_to_tile(x, y, z)
            sql = bdgs_tiles_sql(tile_dict, "point")

            with connection.cursor() as cursor:
                cursor.execute(sql)
                tile_file = cursor.fetchone()[0]

            return HttpResponse(
                tile_file, content_type="application/vnd.mapbox-vector-tile"
            )
        else:
            return HttpResponse(status=204)


def get_tile_shape(request, x, y, z):
    # Check the request zoom level
    if int(z) >= 16:
        tile_dict = url_params_to_tile(x, y, z)
        sql = bdgs_tiles_sql(tile_dict, "shape")

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


class DiffView(APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Différences depuis une date donnée",
                "description": (
                    "Liste l'ensemble des modifications apportées au RNB depuis une date données. Génère un fichier CSV. Voici les points importants à retenir : <br />"
                    "<ul>"
                    "<li>Les modifications listées sont de trois types : create, update et delete</li>"
                    "<li>Les modifications sont triées par rnb_id puis par date de modification croissante</li>"
                    "<li>Il est possible qu'un même bâtiment ait plusieurs modifications dans la période considérée. Par exemple, une création (create) suivie d'une mise à jour (update)</li>"
                    "</ul>"
                ),
                "operationId": "getDiff",
                "parameters": [
                    {
                        "name": "since",
                        "in": "query",
                        "description": (
                            "Date et heure à partir de laquelle les modifications sont retournées. Le format est ISO 8601. <br />"
                            "Seules les dates après le 1er avril 2024 sont acceptées.<br/>"
                            "Une date antérieure reviendrait à télécharger l'intégralité de la base de données (l'ensemble de la base est <a href='https://www.data.gouv.fr/fr/datasets/referentiel-national-des-batiments/'>disponible ici</a>). "
                        ),
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "2024-04-02T00:00:00Z",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Fichier CSV listant l'ensemble des opérations ayant modifié le RNB depuis la date indiquée.",
                        "content": {
                            "text/csv": {
                                "schema": {"type": "string"},
                                "example": (
                                    "action,rnb_id,status,sys_period,point,shape,addresses_id,ext_ids"
                                ),
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request):

        # Alternative idea:
        # In case the streaming solution becomes a problem (might be because of the process fork or any other reason), here is another idea for avoiding relying too heavily on the database:
        # Since the list of modifications between two dates is static, we could precalculate large time chunks (eg: one each month) and save those results in CSV files. When the diff endpoint is requested, we could assemble some of those large CSV chunks into one, add remaining rows to complete the time period by fetching them from db and finally serve the combined file.

        since_input = request.GET.get("since", "")
        # parse since to a timestamp
        since = parse_datetime(since_input)

        if since is None:
            return HttpResponse(
                "The 'since' parameter is missing or incorrect", status=400
            )
        # nobody should download the whole database
        elif since < parse_datetime("2024-04-01T00:00:00Z"):
            return HttpResponse(
                "The 'since' parameter must be after 2024-04-01T00:00:00Z",
                status=400,
            )

        with connection.cursor() as cursor:
            most_recent_modification_query = sql.SQL(
                """
                select max(lower(sys_period)) from batid_building_with_history
                """
            )
            cursor.execute(most_recent_modification_query)
            most_recent_modification = cursor.fetchone()[0]
            most_recent_modification = most_recent_modification.isoformat(sep="T")

        # file descriptors r, w for reading and writing
        r, w = os.pipe()
        # the process is forked
        # would it be possible to avoid creating a new process
        # and keep the streaming feature?
        # https://stackoverflow.com/questions/78998534/stream-data-from-postgres-to-http-request-using-django-streaminghttpresponse?noredirect=1#comment139290268_78998534
        processid = os.fork()

        if processid:
            # This is the parent process
            # the parent will only read data coming from the child process, we can close w
            os.close(w)
            # data coming from the child process arrives here
            r = os.fdopen(r)
            return StreamingHttpResponse(
                r,
                content_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="diff_{since.isoformat()}_{most_recent_modification}.csv"'
                },
            )
        else:
            # This is the child process
            # the child will only write data, we can close r
            os.close(r)
            w = os.fdopen(w, "w")

            with connection.cursor() as cursor:
                sql_query = sql.SQL(
                    """
                    COPY (
                        select
                        CASE
                            WHEN event_type = 'deletion' THEN 'delete'
                            WHEN event_type = 'update' THEN 'update'
                            WHEN event_type = 'split' and not is_active THEN 'delete'
                            WHEN event_type = 'split' and is_active THEN 'create'
                            WHEN event_type = 'merge' and not is_active THEN 'delete'
                            WHEN event_type = 'merge' and is_active THEN 'create'
                            ELSE 'create'
                        END as action,
                        rnb_id, status, sys_period, ST_AsEWKT(point) as point, ST_AsEWKT(shape) as shape, addresses_id, ext_ids from batid_building_with_history bb
                        where lower(sys_period) > {start}::timestamp with time zone and lower(sys_period) <= {end}::timestamp with time zone order by rnb_id, lower(sys_period)
                    ) TO STDOUT WITH CSV HEADER
                    """
                ).format(
                    start=sql.Literal(since.isoformat()),
                    end=sql.Literal(most_recent_modification),
                )
                # the data coming from the query is streamed to the file descriptor w
                # and will be received by the parent process as a stream
                cursor.copy_expert(sql_query, w)
            w.close()
            # the child process is terminated
            os._exit(0)


@extend_schema(exclude=True)
class ContributionsViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer

    def create(self, request, *args, **kwargs):
        serializer = ContributionSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            if request.query_params.get("ranking") == "true" and request.data.get(
                "email"
            ):
                count, rank = get_contributor_count_and_rank(request.data.get("email"))
                response = dict(serializer.data)
                response["contributor_count"] = count
                response["contributor_rank"] = rank
                return Response(response, status=201)
            else:
                return Response(serializer.data, status=201)
        else:
            return Response(serializer.errors, status=400)

    @action(detail=False, methods=["get"])
    def ranking(self, request, *args, **kwargs):
        individual = individual_ranking()
        departement = departement_ranking()
        city = city_ranking()
        all_contributions = Contribution.objects.filter(
            status__in=["fixed", "pending"],
            created_at__lt=timezone.make_aware(datetime(2024, 9, 4)),
        ).count()
        data = {
            "individual": individual,
            "city": city,
            "departement": departement,
            "global": all_contributions,
        }
        return Response(data, status=200)


def get_contributor_count_and_rank(email):
    rawSql = """
    with ranking as (select email, count(*) as count, rank() over(order by count(*) desc) from batid_contribution where email is not null and email != '' and status != 'refused' group by email order by count desc)
    select count, rank from ranking where email = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql, [email])
        results = cursor.fetchall()
        target_count, target_rank = results[0]

        return (target_count, target_rank)


def individual_ranking():
    rawSql = """
    select count(*) as count, rank() over(order by count(*) desc)
    from batid_contribution
    where email is not null and email != '' and status != 'refused' and created_at < '2024-09-04'
    group by email
    order by count desc;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql)
        results = cursor.fetchall()
        return results


def departement_ranking():
    rawSql = """
    select d.code, d.name, count(*) as count_dpt
    from batid_contribution c
    left join batid_building b on c.rnb_id = b.rnb_id
    left join batid_department_subdivided d on ST_Contains(d.shape, b.point)
    where c.status != 'refused' and c.created_at < '2024-09-04'
    group by d.code, d.name
    order by count_dpt desc, d.code asc;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql)
        results = cursor.fetchall()
        return results


def city_ranking():
    rawSql = """
    select city.code_insee, city.name, count(*) as count_city
    from batid_contribution c
    inner join batid_building b on c.rnb_id = b.rnb_id
    inner join batid_city city on ST_Contains(city.shape, b.point)
    where c.status != 'refused' and c.created_at < '2024-09-04'
    group by city.code_insee, city.name
    order by count_city desc, city.code_insee asc;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql)
        results = cursor.fetchall()
        return results


@extend_schema(exclude=True)
class AdsTokenView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                json_users = json.loads(request.body)
                users = []

                for json_user in json_users:
                    password = User.objects.make_random_password(length=15)
                    user, created = User.objects.get_or_create(
                        username=json_user["username"],
                        defaults={
                            "email": json_user.get("email", None),
                            "password": password,
                        },
                    )

                    group, created = Group.objects.get_or_create(name=ADS_GROUP_NAME)
                    user.groups.add(group)
                    user.save()

                    organization, created = Organization.objects.get_or_create(
                        name=json_user["organization_name"],
                        defaults={
                            "managed_cities": json_user["organization_managed_cities"]
                        },
                    )

                    organization.users.add(user)
                    organization.save()

                    token, created = Token.objects.get_or_create(user=user)

                    users.append(
                        {
                            "username": user.username,
                            "organization_name": json_user["organization_name"],
                            "email": user.email,
                            "password": password,
                            "token": token.key,
                        }
                    )

                return JsonResponse({"created_users": users})
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)


class TokenScheme(OpenApiAuthenticationExtension):
    target_class = "rest_framework.authentication.TokenAuthentication"
    name = "RNBTokenAuth"
    priority = 1

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Toutes les requêtes liées aux ADS doivent faire l’objet d’une authentification. "
            "Pour vous identifier, utilisez le token fourni par l’équipe du RNB. "
            "Pour faire une demande de token, renseignez ce formulaire.\n\n"
            "Ajoutez une clé `Authorization` aux headers HTTP de chacune de vos requêtes. "
            "La valeur doit être votre token préfixé de la chaîne “Token”. "
            "Un espace sépare “Token” et votre token.\n\n"
            "Exemple:\n\n"
            "`Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b`",
        }


def get_schema(request):

    import yaml

    schema_dict = build_schema_dict()
    schema_yml = yaml.dump(
        schema_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
    )

    response = HttpResponse(schema_yml, content_type="application/x-yaml")
    response["Content-Disposition"] = 'attachment; filename="schema.yml"'

    return response
