from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.permissions import ReadOnly
from api_alpha.serializers.report import ReportSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from batid.models import Report


class GetReport(RNBLoggingMixin, APIView):
    permission_classes = [ReadOnly]

    def get(self, request: Request, report_id: int) -> Response:
        report = get_object_or_404(Report, id=report_id)
        serializer = ReportSerializer(report)
        return Response(serializer.data)
