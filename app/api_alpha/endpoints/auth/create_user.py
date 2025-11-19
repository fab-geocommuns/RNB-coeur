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
import private_captcha


def create_user_in_sandbox(user_data: dict) -> None:
    user_data_without_password = {
        "first_name": user_data["first_name"],
        "last_name": user_data["last_name"],
        "email": user_data["email"],
        "username": user_data["username"],
        "organization_name": user_data.get("organization_name", None),
        "job_title": user_data.get("job_title", None),
    }
    create_sandbox_user.delay(user_data_without_password)


def is_captcha_valid(captcha_solution: str) -> bool:
    client = private_captcha.Client(api_key=settings.PRIVATE_CAPTCHA_API_KEY)
    result = client.verify(solution=captcha_solution)
    return result.success


def validate_captcha(captcha_solution: str) -> None:
    if settings.ENVIRONMENT == "sandbox":
        return

    if not is_captcha_valid(captcha_solution):
        raise BadRequest(detail="Captcha verification failed")


class CreateUserView(APIView):
    throttle_scope = "create_user"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        request_data = request.data
        if isinstance(request_data, QueryDict):
            request_data = request_data.dict()
        validate_captcha(request_data.get("captcha_solution"))
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
