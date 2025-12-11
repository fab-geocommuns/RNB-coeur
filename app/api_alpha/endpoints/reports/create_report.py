from rest_framework import serializers
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.serializers.report import ReportSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.validators import bdg_is_active
from batid.models import Building
from batid.models import Report
from batid.services.rnb_id import clean_rnb_id


class CreateReportSerializer(serializers.Serializer):
    rnb_id = serializers.CharField(max_length=12, required=True)
    text = serializers.CharField(required=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_rnb_id(self, value: str) -> str:
        """
        Validate that the rnb_id exists and corresponds to an active building.
        Note: later on we will allow for reports not linked to a building.
        """
        cleaned_rnb_id = clean_rnb_id(value)
        bdg_is_active(cleaned_rnb_id)
        return cleaned_rnb_id


class CreateReportView(RNBLoggingMixin, APIView):
    throttle_scope = "create_report"

    def post(self, request: Request) -> Response:
        input_serializer = CreateReportSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.validated_data
        rnb_id = data["rnb_id"]
        text = data["text"]
        email = data.get("email")

        building = Building.objects.filter(rnb_id=rnb_id).first()

        assert (
            building is not None
        )  # nosec B101: This is for typing as it's already checked by the serializer

        authenticated_user = request.user if request.user.is_authenticated else None

        report = Report.create(
            point=building.point,  # type: ignore
            building=building,
            text=text,
            email=email,
            user=authenticated_user,
            tags=["Signalement utilisateur"],
        )

        serializer = ReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
