from django.contrib.gis.geos import Point
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.permissions import ReadOnly
from api_alpha.serializers.report import ReportSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from batid.models import Building
from batid.models import Report
from batid.services.rnb_id import clean_rnb_id


class CreateReportSerializer(serializers.Serializer):
    rnb_id = serializers.CharField(max_length=12, required=True)
    text = serializers.CharField(required=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_rnb_id(self, value):
        """
        Validate that the rnb_id exists and corresponds to an active building.
        Note: later on we will allow for reports not linked to a building.
        """
        cleaned_rnb_id = clean_rnb_id(value)
        try:
            building = Building.objects.get(rnb_id=cleaned_rnb_id, is_active=True)
            return cleaned_rnb_id
        except Building.DoesNotExist:
            raise serializers.ValidationError(
                f"Building with rnb_id '{value}' not found or inactive."
            )


class CreateReportView(RNBLoggingMixin, APIView):
    def post(self, request: Request) -> Response:
        serializer = CreateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        rnb_id = data["rnb_id"]
        text = data["text"]
        email = data.get("email", None)

        building = Building.objects.filter(rnb_id=rnb_id).first()

        authenticated_user = request.user if request.user.is_authenticated else None

        report = Report.create(
            point=building.point,
            building=building,
            text=text,
            email=email,
            user=authenticated_user,
            tags=[],
        )

        serializer = ReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
