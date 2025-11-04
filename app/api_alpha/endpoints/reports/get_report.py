from datetime import datetime
from datetime import timezone

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.exceptions import BadRequest
from api_alpha.exceptions import ServiceUnavailable
from api_alpha.pagination import BuildingListingCursorPagination
from api_alpha.pagination import OGCApiPagination
from api_alpha.permissions import ReadOnly
from api_alpha.permissions import RNBContributorPermission
from api_alpha.serializers.serializers import BuildingCreateSerializer
from api_alpha.serializers.serializers import BuildingGeoJSONSerializer
from api_alpha.serializers.serializers import BuildingSerializer
from api_alpha.serializers.serializers import ListBuildingQuerySerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import get_status_html_list
from api_alpha.utils.rnb_doc import get_status_list
from api_alpha.utils.rnb_doc import rnb_doc
from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.exceptions import InvalidOperation
from batid.list_bdg import list_bdgs
from batid.models import Building
from batid.models import Contribution
from batid.models import Report
from api_alpha.serializers.report import ReportSerializer
from django.shortcuts import get_object_or_404


class GetReport(RNBLoggingMixin, APIView):
    permission_classes = [ReadOnly]

    def get(self, request: Request, report_id: int) -> Response:
        report = get_object_or_404(Report, id=report_id)
        serializer = ReportSerializer(report)
        return Response(serializer.data)
