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
from django.http import HttpRequest
from django.http import JsonResponse
from django.http import QueryDict
from django.http import StreamingHttpResponse
from django.utils.dateparse import parse_datetime
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
from dateutil.relativedelta import relativedelta


def get_datetime_april_2024() -> datetime:
    return datetime(2024, 4, 1, 0, 0, 0, tzinfo=timezone.utc)


class DiffView(APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Différences depuis une date donnée",
                "description": (
                    "Liste l'ensemble des modifications apportées au RNB depuis une date données. Génère un fichier CSV. Voici les points importants à retenir : <br />"
                    "<ul>"
                    "<li>Les modifications listées sont de trois types : create, update et delete</li>"
                    "<li>Les modifications sont triées par date de modification croissante</li>"
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
    def get(self, request: HttpRequest) -> HttpResponse | StreamingHttpResponse:

        # Alternative idea:
        # In case the streaming solution becomes a problem (might be because of the process fork or any other reason), here is another idea for avoiding relying too heavily on the database:
        # Since the list of modifications between two dates is static, we could precalculate large time chunks (eg: one each month) and save those results in CSV files. When the diff endpoint is requested, we could assemble some of those large CSV chunks into one, add remaining rows to complete the time period by fetching them from db and finally serve the combined file.

        since_input = request.GET.get("since", "")
        # parse since to a timestamp
        since = parse_datetime(since_input)
        last_available_modification = get_datetime_april_2024()
        if since is None:
            return HttpResponse(
                "The 'since' parameter is missing or incorrect", status=400
            )
        # nobody should download the whole database
        elif since < last_available_modification:
            return HttpResponse(
                "The 'since' parameter must be after 2024-04-01T00:00:00Z",
                status=400,
            )

        local_statement_timeout = settings.DIFF_VIEW_POSTGRES_STATEMENT_TIMEOUT
        with connection.cursor() as cursor:
            cursor.execute(
                "SET statement_timeout = %(statement_timeout)s;",
                {"statement_timeout": local_statement_timeout},
            )
            most_recent_modification_query = sql.SQL(
                """
                select max(lower(sys_period)) from batid_building_with_history
                """
            )
            cursor.execute(most_recent_modification_query)
            most_recent_modification = cursor.fetchone()[0]

        # file descriptors r, w for reading and writing
        rfd, wfd = os.pipe()
        # the process is forked
        # would it be possible to avoid creating a new process
        # and keep the streaming feature?
        # https://stackoverflow.com/questions/78998534/stream-data-from-postgres-to-http-request-using-django-streaminghttpresponse?noredirect=1#comment139290268_78998534
        processid = os.fork()

        if processid:
            # This is the parent process
            # the parent will only read data coming from the child process, we can close w
            os.close(wfd)
            # data coming from the child process arrives here
            r = os.fdopen(rfd)
            return StreamingHttpResponse(
                r,
                content_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="diff_{since.isoformat()}_{most_recent_modification.isoformat()}.csv"'
                },
            )
        else:
            # This is the child process
            # the child will only write data, we can close r
            os.close(rfd)
            w = os.fdopen(wfd, "w")

            with connection.cursor() as cursor:
                cursor.execute(
                    "SET statement_timeout = %(statement_timeout)s;",
                    {"statement_timeout": local_statement_timeout},
                )
                start_ts = since
                first_query = True

                while start_ts < most_recent_modification:
                    end_ts = start_ts + timedelta(days=1)

                    raw_sql = """
                        COPY (
                            select
                            CASE
                                WHEN event_type = 'delete' THEN 'deactivate'
                                WHEN event_type = 'deactivation' THEN 'deactivate'
                                WHEN event_type = 'update' THEN 'update'
                                WHEN event_type = 'split' and not is_active THEN 'deactivate'
                                WHEN event_type = 'split' and is_active THEN 'create'
                                WHEN event_type = 'merge' and not is_active THEN 'deactivate'
                                WHEN event_type = 'merge' and is_active THEN 'create'
                                ELSE 'create'
                            END as action,
                            rnb_id,
                            status,
                            is_active::int,
                            sys_period,
                            ST_AsEWKT(point) as point,
                            ST_AsEWKT(shape) as shape,
                            to_json(addresses_id) as addresses_id,
                            COALESCE(ext_ids, '[]'::jsonb) as ext_ids,
                            parent_buildings,
                            event_id,
                            event_type
                            FROM batid_building_with_history bb
                            where lower(sys_period) > {start}::timestamp with time zone and lower(sys_period) <= {end}::timestamp with time zone
                            order by lower(sys_period)
                        ) TO STDOUT WITH CSV
                        """

                    if first_query:
                        raw_sql = raw_sql + " HEADER"
                        first_query = False

                    sql_query = sql.SQL(raw_sql).format(
                        start=sql.Literal(start_ts.isoformat()),
                        end=sql.Literal(end_ts.isoformat()),
                    )
                    # the data coming from the query is streamed to the file descriptor w
                    # and will be received by the parent process as a stream
                    cursor.copy_expert(sql_query, w)
                    start_ts = end_ts
            w.close()
            # the child process is terminated
            os._exit(0)
