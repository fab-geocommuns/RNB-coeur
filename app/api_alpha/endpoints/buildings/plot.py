import binascii
import json
import os
import urllib.parse
from datetime import datetime
from datetime import timedelta
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
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils.dateparse import parse_datetime
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse
from psycopg2 import sql
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
from api_alpha.serializers.serializers import BuildingPlotSerializer
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
from batid.exceptions import PlotUnknown
from batid.models import ADS
from batid.models import Building
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
from batid.models import SummerChallenge
from batid.services.bdg_on_plot import get_buildings_on_plot
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
from batid.utils.constants import ADS_GROUP_NAME


class BuildingPlotView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Bâtiments sur une parcelle cadastrale",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments présents sur une parcelle cadastrale. Les bâtiments sont triés par taux de recouvrement décroissant entre le bâtiment et la parcelle (le bâtiment entièrement sur une parcelle arrive avant celui à moitié sur la parcelle). La méthode de filtrage est purement géométrique et ne tient pas compte du lien fiscal entre le bâtiment et la parcelle. Des faux positifs sont donc possibles. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "plotBuildings",
                "parameters": [
                    {
                        "name": "plot_id",
                        "in": "path",
                        "description": "Identifiant de la parcelle cadastrale.",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "01402000AB0051",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments présents sur la parcelle cadastrale",
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
                                                        "type": "number",
                                                        "name": "bdg_cover_ratio",
                                                        "description": "Taux d'intersection entre le bâtiment et la parcelle. Ce taux est compris entre 0 et 1. Un taux de 1 signifie que la parcelle couvre entièrement le bâtiment.",
                                                        "example": 0.65,
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
    def get(self, request, plot_id, *args, **kwargs):
        try:
            bdgs = get_buildings_on_plot(plot_id)
        except PlotUnknown:
            raise NotFound("Plot unknown")

        paginator = BuildingCursorPagination()
        paginated_bdgs = paginator.paginate_queryset(bdgs, request)
        serializer = BuildingPlotSerializer(paginated_bdgs, many=True)

        return paginator.get_paginated_response(serializer.data)
