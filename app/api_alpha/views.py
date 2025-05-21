import binascii
import json
import os
from base64 import b64encode
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
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.db import connection
from django.db import transaction
from django.http import HttpResponse
from django.http import JsonResponse
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils.dateparse import parse_datetime
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse
from psycopg2 import sql
from rest_framework import mixins
from rest_framework import status
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ParseError
from rest_framework.pagination import BasePagination
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView
from rest_framework_tracking.models import APIRequestLog

from api_alpha.apps import LiteralStr
from api_alpha.exceptions import BadRequest
from api_alpha.exceptions import ServiceUnavailable
from api_alpha.permissions import ADSPermission
from api_alpha.permissions import ReadOnly
from api_alpha.permissions import RNBContributorPermission
from api_alpha.serializers import ADSSerializer
from api_alpha.serializers import BuildingAddressQuerySerializer
from api_alpha.serializers import BuildingClosestQuerySerializer
from api_alpha.serializers import BuildingClosestSerializer
from api_alpha.serializers import BuildingCreateSerializer
from api_alpha.serializers import BuildingMergeSerializer
from api_alpha.serializers import BuildingPlotSerializer
from api_alpha.serializers import BuildingSerializer
from api_alpha.serializers import BuildingSplitSerializer
from api_alpha.serializers import BuildingUpdateSerializer
from api_alpha.serializers import ContributionSerializer
from api_alpha.serializers import DiffusionDatabaseSerializer
from api_alpha.serializers import GuessBuildingSerializer
from api_alpha.typeddict import SplitCreatedBuilding
from api_alpha.utils.parse_boolean import parse_boolean
from api_alpha.utils.rnb_doc import build_schema_dict
from api_alpha.utils.rnb_doc import get_status_html_list
from api_alpha.utils.rnb_doc import get_status_list
from api_alpha.utils.rnb_doc import rnb_doc
from api_alpha.utils import IsSuperUser
from api_alpha.utils import RNBLoggingMixin
from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.exceptions import BuildingTooLarge
from batid.exceptions import ImpossibleShapeMerge
from batid.exceptions import InvalidWGS84Geometry
from batid.exceptions import NotEnoughBuildings
from batid.exceptions import OperationOnInactiveBuilding
from batid.exceptions import PlotUnknown
from batid.list_bdg import list_bdgs
from batid.models import ADS
from batid.models import Building
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
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
from batid.services.vector_tiles import ads_tiles_sql
from batid.services.vector_tiles import bdgs_tiles_sql
from batid.services.vector_tiles import plots_tiles_sql
from batid.services.vector_tiles import url_params_to_tile
from batid.utils.auth import make_random_password
from batid.utils.constants import ADS_GROUP_NAME


def get_schema(request):
    schema_dict = build_schema_dict()
    schema_yml = yaml.dump(
        schema_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
    )

    response = HttpResponse(schema_yml, content_type="application/x-yaml")
    response["Content-Disposition"] = 'attachment; filename="schema.yml"'

    return response
