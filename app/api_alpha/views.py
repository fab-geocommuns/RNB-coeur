import binascii
import json
import urllib.parse
from datetime import datetime
from datetime import timezone
from typing import Any

import requests
import yaml
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import connection
from django.db import transaction
from django.db.models import Q
from django.db.models import Sum
from django.http import HttpResponse
from django.http import JsonResponse
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse
from rest_framework import mixins
from rest_framework import status
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_tracking.models import APIRequestLog

from api_alpha.apps import LiteralStr
from api_alpha.exceptions import BadRequest
from api_alpha.exceptions import ServiceUnavailable
from api_alpha.pagination import BuildingAddressCursorPagination
from api_alpha.pagination import BuildingCursorPagination
from api_alpha.permissions import ADSPermission
from api_alpha.permissions import RNBContributorPermission
from api_alpha.serializers.serializers import ADSSerializer
from api_alpha.serializers.serializers import BuildingAddressQuerySerializer
from api_alpha.serializers.serializers import BuildingClosestQuerySerializer
from api_alpha.serializers.serializers import BuildingClosestSerializer
from api_alpha.serializers.serializers import BuildingMergeSerializer
from api_alpha.serializers.serializers import BuildingSerializer
from api_alpha.serializers.serializers import BuildingSplitSerializer
from api_alpha.serializers.serializers import ContributionSerializer
from api_alpha.serializers.serializers import DiffusionDatabaseSerializer
from api_alpha.serializers.serializers import GuessBuildingSerializer
from api_alpha.serializers.serializers import OrganizationSerializer
from api_alpha.serializers.serializers import UserSerializer
from api_alpha.typeddict import SplitCreatedBuilding
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from api_alpha.utils.rnb_doc import get_status_list
from api_alpha.utils.rnb_doc import rnb_doc
from api_alpha.utils.sandbox_client import SandboxClient
from api_alpha.utils.sandbox_client import SandboxClientError
from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.exceptions import InvalidOperation
from batid.models import ADS
from batid.models import Building
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
from batid.models import SummerChallenge
from batid.services.closest_bdg import get_closest_from_point
from batid.services.email import build_reset_password_email
from batid.services.geocoders import BanGeocoder
from batid.services.guess_bdg import BuildingGuess
from batid.services.kpi import get_kpi_most_recent
from batid.services.kpi import KPI_ACTIVE_BUILDINGS_COUNT
from batid.services.rnb_id import clean_rnb_id
from batid.services.search_ads import ADSSearch
from batid.services.user import get_user_id_b64
from batid.services.user import get_user_id_from_b64
from batid.tasks import create_sandbox_user
from batid.utils.auth import make_random_password


class BuildingGuessView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Identification de bâtiment",
                "description": (
                    "Cet endpoint permet d'identifier le bâtiment correspondant à une série de critères. Il permet d'accueillir des données imprécises et tente de les combiner pour fournir le meilleur résultat. NB : l'URL se termine nécessairement par un slash (/)."
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

        if not search.is_valid():
            return Response(
                {"errors": search.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            qs = search.get_queryset()
            serializer = GuessBuildingSerializer(qs, many=True)

            return Response(serializer.data)
        except BANAPIDown:
            raise ServiceUnavailable(detail="BAN API is currently down")


class BuildingClosestView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Bâtiments les plus proches d'un point",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments présents dans un rayon donné autour d'un point donné. Les bâtiments sont triés par distance croissante par rapport au point donné. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "closestBuildings",
                "parameters": [
                    {
                        "name": "point",
                        "in": "query",
                        "description": "Latitude et longitude, séparées par une virgule, du point de recherche.",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "44.8201164915397,-0.5717449803671368",
                    },
                    {
                        "name": "radius",
                        "in": "query",
                        "description": "Rayon de recherche en mètres, autour du point. Compris entre 0 et 1000 mètres.",
                        "required": True,
                        "schema": {"type": "number"},
                        "example": 1000,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments les plus proches du point donné",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "URL de la page de résultats suivante",
                                            "nullable": True,
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "URL de la page de résultats précédente",
                                            "nullable": True,
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "type": "object",
                                                        "properties": {
                                                            "distance": {
                                                                "type": "number",
                                                                "format": "float",
                                                                "example": 6.78,
                                                                "description": "Distance en mètres entre le bâtiment et le point donné",
                                                            },
                                                        },
                                                    },
                                                ]
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, *args, **kwargs):
        query_serializer = BuildingClosestQuerySerializer(data=request.query_params)

        if query_serializer.is_valid():

            point = request.query_params.get("point")
            radius = request.query_params.get("radius")
            lat, lng = point.split(",")
            lat = float(lat)
            lng = float(lng)
            radius = float(radius)

            # Get results and paginate
            bdgs = get_closest_from_point(lat, lng, radius)
            paginator = BuildingCursorPagination()
            paginated_bdgs = paginator.paginate_queryset(bdgs, request)
            serializer = BuildingClosestSerializer(paginated_bdgs, many=True)

            return paginator.get_paginated_response(serializer.data)

        else:
            # Invalid data, return validation errors
            return Response(query_serializer.errors, status=400)


class BuildingAddressView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Identification de bâtiments par leur adresse",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments associés à une adresse. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "address",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "description": "Adresse texte non structurée. L'adresse fournie est recherchée dans la BAN afin de récupérer la clé d'interopérabilité associée. C'est via cette clé que sont filtrés les bâtiments. Si le geocodage échoue aucun résultat n'est renvoyé et le champ **status** de la réponse contient **geocoding_no_result**",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "4 rue scipion, 75005 Paris",
                    },
                    {
                        "name": "min_score",
                        "in": "query",
                        "description": "Score minimal attendu du géocodage BAN. Valeur par défaut : **0.8**. Si le score est strictement inférieur à cette limite, aucun résultat n'est renvoyé et le champ **status** de la réponse contient **geocoding_score_is_too_low**",
                        "required": False,
                        "schema": {"type": "float"},
                        "example": "0.9",
                    },
                    {
                        "name": "cle_interop_ban",
                        "in": "query",
                        "description": "Clé d'interopérabilité BAN. Si vous êtes en possession d'une clé d'interoperabilité, il est plus efficace de faire une recherche grâce à elle que via une adresse textuelle.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75105_8884_00004",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments associés à l'adresse donnée.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "URL de la page de résultats suivante",
                                            "nullable": True,
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "URL de la page de résultats précédente",
                                            "nullable": True,
                                        },
                                        "cle_interop_ban": {
                                            "type": "string",
                                            "description": "Clé d'interopérabilité BAN utilisée pour lister les bâtiments",
                                            "nullable": True,
                                        },
                                        "status": {
                                            "type": "string",
                                            "description": "'geocoding_score_is_too_low' si le géocodage BAN renvoie un score inférieur à 'min_score'. 'geocoding_no_result' si le géocodage ne renvoie pas de résultats. 'ok' sinon",
                                            "nullable": False,
                                        },
                                        "score_ban": {
                                            "type": "float",
                                            "description": "Si un géocodage a lieu, renvoie le score du meilleur résultat, celui utilisé pour lister les bâtiments. Ce score doit être supérieur à 'min_score' pour que des bâtiments soient renvoyés.",
                                            "nullable": False,
                                        },
                                        "results": {
                                            "type": "array",
                                            "nullable": True,
                                            "items": {
                                                "$ref": "#/components/schemas/Building"
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, *args, **kwargs):
        query_serializer = BuildingAddressQuerySerializer(data=request.query_params)
        infos: dict[str, Any] = {
            "cle_interop_ban": None,
            "score_ban": None,
            "status": None,
        }

        if query_serializer.is_valid():
            q = request.query_params.get("q")
            paginator = BuildingAddressCursorPagination()

            if q:
                # 0.8 is the default value
                min_score = float(request.query_params.get("min_score", 0.8))
                geocoder = BanGeocoder()
                try:
                    best_result = geocoder.cle_interop_ban_best_result({"q": q})
                except BANAPIDown:
                    raise ServiceUnavailable(detail="BAN API is currently down")
                cle_interop_ban = best_result["cle_interop_ban"]
                score = best_result["score"]

                infos["cle_interop_ban"] = cle_interop_ban
                infos["score_ban"] = score

                if cle_interop_ban is None:
                    infos["status"] = "geocoding_no_result"
                    return paginator.get_paginated_response(None, infos)
                if score is not None and score < min_score:
                    infos["status"] = "geocoding_score_is_too_low"
                    return paginator.get_paginated_response(None, infos)
            else:
                cle_interop_ban = request.query_params.get("cle_interop_ban")
                infos["cle_interop_ban"] = cle_interop_ban

            infos["status"] = "ok"
            buildings = (
                Building.objects.filter(is_active=True)
                .filter(addresses_read_only__id=cle_interop_ban)
                .prefetch_related("addresses_read_only")
            )
            paginated_bdgs = paginator.paginate_queryset(buildings, request)
            serialized_buildings = BuildingSerializer(paginated_bdgs, many=True)

            return paginator.get_paginated_response(serialized_buildings.data, infos)
        else:
            # Invalid data, return validation errors
            return Response(query_serializer.errors, status=400)


class MergeBuildings(RNBLoggingMixin, APIView):
    permission_classes = [RNBContributorPermission]

    @rnb_doc(
        {
            "post": {
                "summary": "Fusion de bâtiments",
                "description": LiteralStr(
                    """\
Permet de corriger le RNB en fusionnant plusieurs bâtiments existants, donnant lieu à la création d'un nouveau bâtiment.

Cet endpoint nécessite d'être identifié et d'avoir des droits d'édition du RNB.
                """
                ),
                "operationId": "mergeBuildings",
                "parameters": [],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": """Commentaire optionnel associé à l'opération""",
                                    },
                                    "rnb_ids": {
                                        "type": "array",
                                        "description": "Liste des ID-RNB des bâtiments à fusionner",
                                        "exemple": ["XXXXYYYYZZZZ", "AAAABBBBCCCC"],
                                    },
                                    "merge_existing_addresses": {
                                        "type": "bool",
                                        "description": LiteralStr(
                                            """\
- `True`, le bâtiment nouvellement créé hérite des adresses des bâtiments dont il est issu.
- `False` ou non rempli, le champ `addresses_cle_interop` est utilisé pour déterminer les adresses du bâtiment."""
                                        ),
                                    },
                                    "addresses_cle_interop": {
                                        "type": "array",
                                        "description": "Liste des clés d'interopérabilité BAN liées au nouveau bâtiment créé. Si une liste vide est passée, le bâtiment ne sera lié à aucune adresse.",
                                        "exemple": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": get_status_list(),
                                        "description": "Statut du bâtiment.",
                                        "example": "constructed",
                                    },
                                },
                                "required": ["rnb_ids", "status"],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment nouvellement créé",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/Building"},
                                    ]
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            }
        }
    )
    def post(self, request):
        serializer = BuildingMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user

        with transaction.atomic():
            contribution = Contribution(
                text=data.get("comment"),
                status="fixed",
                status_changed_at=datetime.now(timezone.utc),
                report=False,
                review_user=user,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            rnb_ids = data.get("rnb_ids")
            buildings = []
            for rnb_id in rnb_ids:
                building = get_object_or_404(Building, rnb_id=rnb_id)
                buildings.append(building)

            status = data.get("status")

            merge_existing_addresses = data.get("merge_existing_addresses")
            if merge_existing_addresses:
                addresses_id = [
                    address
                    for building in buildings
                    for address in building.addresses_id
                ]
            else:
                addresses_id = data.get("addresses_cle_interop")

            # remove possible duplicates
            addresses_id = list(set(addresses_id))

            try:
                new_building = Building.merge(
                    buildings, user, event_origin, status, addresses_id
                )
            except BANAPIDown:
                raise ServiceUnavailable(detail="BAN API is currently down")
            except BANUnknownCleInterop:
                raise NotFound(detail="Cle d'intéropérabilité not found on the BAN API")
            except BANBadResultType:
                raise BadRequest(
                    detail="BAN result has not the expected type (must be 'numero')"
                )
            except InvalidOperation as e:
                raise BadRequest(detail=e.api_message_with_details())

            # update the contribution now that the rnb_id is known
            contribution.rnb_id = new_building.rnb_id
            contribution.save()

        serializer = BuildingSerializer(new_building, with_plots=False)
        return Response(serializer.data, status=http_status.HTTP_201_CREATED)


class SplitBuildings(RNBLoggingMixin, APIView):
    permission_classes = [RNBContributorPermission]

    @rnb_doc(
        {
            "post": {
                "summary": "Scission de bâtiments",
                "description": LiteralStr(
                    """\
Permet de corriger le RNB en scindant un bâtiment existant, donnant lieu à la création de plusieurs nouveaux bâtiments.

Cet endpoint nécessite d'être identifié et d'avoir des droits d'édition du RNB."""
                ),
                "operationId": "splitBuildings",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB (ID-RNB)",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    },
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": """Commentaire optionnel associé à l'opération""",
                                    },
                                    "created_buildings": {
                                        "type": "array",
                                        "description": "Liste des bâtiments issus de la scission.",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "status": {
                                                    "type": "string",
                                                    "enum": get_status_list(),
                                                    "description": "Statut du bâtiment.",
                                                    "example": "constructed",
                                                },
                                                "shape": {
                                                    "type": "string",
                                                    "description": "Géométrie du bâtiment au format WKT ou HEX, en WGS84.",
                                                    "example": "POLYGON((2.3522 48.8566, 2.3532 48.8567, 2.3528 48.857, 2.3522 48.8566))",
                                                },
                                                "addresses_cle_interop": {
                                                    "type": "array",
                                                    "description": "Liste des clés interopérables des adresses associées",
                                                    # "items": {"type": "string"},
                                                    "example": [
                                                        "75105_8884_00004",
                                                        "75105_8884_00006",
                                                    ],
                                                },
                                            },
                                            "required": [
                                                "status",
                                                "shape",
                                                "addresses_cle_interop",
                                            ],
                                        },
                                    },
                                },
                                "required": ["rnb_id", "created_buildings"],
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Détails des bâtiments nouvellement créés",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Building"},
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            },
        }
    )
    def post(self, request, rnb_id):
        serializer = BuildingSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user

        with transaction.atomic():
            rnb_id = clean_rnb_id(rnb_id)
            comment = data.get("comment")

            contribution = Contribution(
                text=comment,
                status="fixed",
                status_changed_at=datetime.now(timezone.utc),
                report=False,
                review_user=user,
                rnb_id=rnb_id,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            created_buildings: list[SplitCreatedBuilding] = data.get(
                "created_buildings"
            )

            try:
                building = get_object_or_404(Building, rnb_id=rnb_id)
                new_buildings = building.split(created_buildings, user, event_origin)
            except BANAPIDown:
                raise ServiceUnavailable(detail="BAN API is currently down")
            except BANUnknownCleInterop:
                raise NotFound(detail="Cle d'intéropérabilité not found on the BAN API")
            except BANBadResultType:
                raise BadRequest(
                    detail="BAN result has not the expected type (must be 'numero')"
                )
            except InvalidOperation as e:
                raise BadRequest(detail=e.api_message_with_details())

        serializer = BuildingSerializer(new_buildings, with_plots=False, many=True)
        return Response(serializer.data, status=http_status.HTTP_201_CREATED)


class ADSBatchViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = ADS.objects.all()  # type: ignore[assignment]
    serializer_class = ADSSerializer  # type: ignore[assignment]
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
    queryset = ADS.objects.all()  # type: ignore[assignment]
    serializer_class = ADSSerializer  # type: ignore[assignment]
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
            "Cet endpoint permet de créer une Autorisation du Droit des Sols (ADS) dans le RNB. "
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
            "Cet endpoint permet de modifier une Autorisation du Droit des Sols (ADS) existante dans le RNB. "
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
        description="Cet endpoint permet de supprimer une Autorisation du Droit des Sols (ADS) existante dans le RNB.",
        responses={
            204: {"description": "ADS supprimée avec succès"},
            404: {"description": "ADS non trouvée"},
        },
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


def get_data_gouv_publication_count():
    # call data.gouv.fr API to get the number of datasets
    req = requests.get("https://www.data.gouv.fr/api/1/datasets/?tag=rnb")
    if req.status_code != 200:
        return None
    else:
        # remove the dataset that is the RNB
        return req.json()["total"] - 1


def get_stats(request):

    api_calls_since_2024_count = APIRequestLog.objects.filter(
        requested_at__gte="2024-01-01T00:00:00Z"
    ).count()
    reports_count = Contribution.objects.filter(report=True).count()
    editions_count = Contribution.objects.filter(report=False).count()
    data_gouv_publication_count = get_data_gouv_publication_count()
    diffusion_databases_count = DiffusionDatabase.objects.count()

    # Get the cached value of the building count
    bdg_count_kpi = get_kpi_most_recent(KPI_ACTIVE_BUILDINGS_COUNT)

    data = {
        "building_counts": bdg_count_kpi.value,
        "api_calls_since_2024_count": api_calls_since_2024_count,
        "reports_count": reports_count,
        "editions_count": editions_count,
        "data_gouv_publication_count": data_gouv_publication_count,
        "diffusion_databases_count": diffusion_databases_count,
    }

    renderer = JSONRenderer()
    response = HttpResponse(renderer.render(data), content_type="application/json")

    return response


@extend_schema(exclude=True)
class ContributionsViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Contribution.objects.all()  # type: ignore[assignment]
    serializer_class = ContributionSerializer  # type: ignore[assignment]

    def create(self, request, *args, **kwargs):
        serializer = ContributionSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        else:
            return Response(serializer.errors, status=400)


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


def summer_challenge_targeted_score():
    return 100_000


def summer_challenge_global_score():
    global_score = SummerChallenge.objects.aggregate(score=Sum("score"))
    return global_score["score"]


def summer_challenge_leaderboard(max_rank):
    global_score = summer_challenge_global_score()

    individual_ranking = (
        SummerChallenge.objects.values_list("user__username")
        .annotate(score=Sum("score"))
        .order_by("-score")[:max_rank]
    )
    individual_ranking = [list(row) for row in individual_ranking]

    city_ranking = (
        SummerChallenge.objects.exclude(city__isnull=True)
        .values_list("city__code_insee", "city__name")
        .annotate(score=Sum("score"))
        .order_by("-score")[:max_rank]
    )
    city_ranking = [list(row) for row in city_ranking]

    departement = (
        SummerChallenge.objects.exclude(department__isnull=True)
        .values_list("department__code", "department__name")
        .annotate(score=Sum("score"))
        .order_by("-score")[:max_rank]
    )
    departement_ranking = [list(row) for row in departement]

    return {
        "goal": summer_challenge_targeted_score(),
        "global": global_score,
        "individual": individual_ranking,
        "city": city_ranking,
        "departement": departement_ranking,
    }


@api_view(["GET"])
def get_summer_challenge_leaderboard(request):
    max_rank = int(request.GET.get("max_rank", 5))
    leaderboard = summer_challenge_leaderboard(max_rank)
    return JsonResponse(leaderboard)


@api_view(["GET"])
def get_summer_challenge_user_score(request, username):

    # Check the user exists, we by ursername or email
    try:
        User.objects.get(
            Q(username=username) | Q(email=username)
        )  # This will raise an exception if the user does not exist
    except User.DoesNotExist:
        raise NotFound()

    global_score = summer_challenge_global_score()
    individual_ranking = (
        SummerChallenge.objects.values("user__username", "user__email")
        .annotate(score=Sum("score"))
        .order_by("-score")
    )

    user_score = 0
    user_rank = None

    for i, rank in enumerate(individual_ranking):
        if rank["user__username"] == username or rank["user__email"] == username:
            user_score = rank["score"]
            user_rank = i + 1
            break

    data = {
        "goal": summer_challenge_targeted_score(),
        "global": global_score,
        "user_score": user_score,
        "user_rank": user_rank,
    }
    return JsonResponse(data)


class RNBAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=response.data["token"])
        user = token.user
        return Response(
            {
                "id": user.id,
                "token": token.key,
                "username": user.username,
                "groups": [group.name for group in user.groups.all()],
            }
        )


def create_user_in_sandbox(user_data: dict) -> None:
    user_data_without_password = {**user_data}
    user_data_without_password.pop("password")
    create_sandbox_user.delay(user_data_without_password)


class CreateUserView(APIView):
    throttle_scope = "create_user"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        request_data = request.data
        if isinstance(request_data, QueryDict):
            request_data = request_data.dict()
        user_serializer = UserSerializer(data=request_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()

        organization_serializer = None
        organization_name = request_data.get("organization_name")
        if organization_name:
            organization_serializer = OrganizationSerializer(
                data={"name": organization_name}
            )
            organization_serializer.is_valid(raise_exception=True)
            organization, created = Organization.objects.get_or_create(
                name=organization_name
            )
            organization.users.add(user)
            organization.save()

        if settings.HAS_SANDBOX:
            create_user_in_sandbox(request_data)

        return Response(
            {
                "user": user_serializer.data,
                "organization": (
                    organization_serializer.data if organization_serializer else None
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class SandboxAuthenticationError(AuthenticationFailed):
    pass


def sandbox_only(func):
    def wrapper(self, request, *args, **kwargs):
        if settings.ENVIRONMENT != "sandbox":
            print("Sandbox only endpoint called in non-sandbox environment")
            raise NotFound()

        auth_header = request.headers.get("Authorization")
        expected_auth_header = f"Bearer {settings.SANDBOX_SECRET_TOKEN}"
        if not settings.SANDBOX_SECRET_TOKEN or auth_header != expected_auth_header:
            raise SandboxAuthenticationError()
        return func(self, request, *args, **kwargs)

    return wrapper


class GetUserToken(APIView):
    @sandbox_only
    def get(self, request, user_email_b64):
        user_email = urlsafe_base64_decode(user_email_b64).decode()
        user = User.objects.get(email=user_email)
        try:
            token = Token.objects.get(user=user)
        except Token.DoesNotExist:
            token = None
        return Response({"token": token.key if token else None})


class GetCurrentUserTokens(APIView):
    permission_classes = [RNBContributorPermission]

    def get(self, request) -> Response:
        user = request.user
        token = Token.objects.get(
            user=user
        )  # Exists because it's used to authenticate the request

        sandbox_token = self._get_sandbox_token(user.email)

        return Response(
            {
                "production_token": token.key if token else None,
                "sandbox_token": sandbox_token,
            }
        )

    def _get_sandbox_token(self, user_email: str) -> str | None:
        if not settings.HAS_SANDBOX:
            return None

        try:
            return SandboxClient().get_user_token(user_email)
        except SandboxClientError:
            return None


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


class DiffusionDatabaseView(APIView):
    def get(self, request):
        """Lists all databases in which ID-RNBs are published and available attributes"""
        databases = DiffusionDatabase.objects.all()
        serializer = DiffusionDatabaseSerializer(databases, many=True)
        return Response(serializer.data)


class OrganizationView(APIView):
    def get(self, request):
        """Lists all organization names"""
        organizations = Organization.objects.all()
        names = [org.name for org in organizations]
        return Response(names)


def get_all_endpoints_schema(request):
    schema_dict = build_schema_all_endpoints()
    schema_yml = yaml.dump(
        schema_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
    )

    response = HttpResponse(schema_yml, content_type="application/x-yaml")
    response["Content-Disposition"] = 'attachment; filename="schema.yml"'

    return response


class ActivateUser(APIView):
    def get(self, request, user_id_b64, token):
        try:
            uid = urlsafe_base64_decode(user_id_b64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        site_url = settings.FRONTEND_URL

        if user and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            return redirect(
                f"{site_url}/activation?status=success&email={urllib.parse.quote(user.email)}"
            )
        else:
            return redirect(f"{site_url}/activation?status=error")


class RequestPasswordReset(APIView):
    def post(self, request):

        email = request.data.get("email")
        if email is None:
            return JsonResponse({"error": "L'adresse email est requise"}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # We do not want someone to know if an email is in the database or not:
            # even if the user does not exist, we still return a 204 status code
            return Response(None, status=204)

        # We found a user with the email, we continue

        # We generate the token. Note, Django does not need to store the "request new password" token in the database
        # (explanation: https://stackoverflow.com/questions/46234627/how-does-default-token-generator-store-tokens)
        token = default_token_generator.make_token(user)

        # We also need the user id in base 64
        user_id_b64 = get_user_id_b64(user)

        # Build the email to send
        email = build_reset_password_email(token, user_id_b64, email)

        # Send the email
        # Might do: use a queue to send the email instead of a synchronous call
        email.send()

        return Response(None, status=204)


class ChangePassword(APIView):

    # About security:
    # This endpoint is used to change the password of a user. It is very sensitive. It should be hardened.
    # - In case of wrong user id/token couple, always return a 404 status code
    # - Throttle the endpoint to avoid brute force attacks
    # - Do not log the use of this endpoint, the risk would be to log the new password in the logs, which is a security risk.
    # - Validate the new password is strong enough (validated against the AUTH_PASSWORD_VALIDATORS validators set in settings.py)

    # about scoped throttles in DRF: https://www.django-rest-framework.org/api-guide/throttling/#scopedratethrottle
    throttle_scope = "change_password"

    def patch(self, request, user_id_b64, token):

        # #################
        # First, we verify the couple user_id/token is valid, otherwise we return a 404 status code

        try:
            # Convert Base 64 user id to string
            user_id = get_user_id_from_b64(user_id_b64)
        except binascii.Error:
            # We return a 404 status code if the user does not exist.
            # We do not provide information about the user or the token.
            return Response(None, status=404)

        # Retrieve the user
        try:

            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            # We return a 404 status code if the user does not exist.
            # We do not provide information about the user or the token.
            return Response(None, status=404)

        # We check if the token is valid
        if not default_token_generator.check_token(user, token):
            # We return a 404 status code if the token is not valid for this user.
            # We do not provide information about the user or the token.
            return Response(None, status=404)

        # #################
        # Second, we verify the new password is valid

        password = request.data.get("password")
        if password is None:
            return JsonResponse(
                {"error": ["Le nouveau mot de passe est requis"]}, status=400
            )

        confirm_password = request.data.get("confirm_password")
        if confirm_password is None:
            return JsonResponse(
                {"error": ["La confirmation du nouveau mot de passe est requise"]},
                status=400,
            )

        if password != confirm_password:
            return JsonResponse(
                {"error": ["Les deux mots de passe ne correspondent pas"]}, status=400
            )

        # Verify the password is strong enough (validated against the AUTH_PASSWORD_VALIDATORS validators set in settings.py)
        try:
            validate_password(password, user)
        except ValidationError as e:
            return JsonResponse({"error": e.messages}, status=400)

        # We change the password
        user.set_password(password)
        user.save()

        return Response(None, status=204)
