from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.serializers.report import ReportSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from batid.models import Report


class ReplyToReportSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, allow_blank=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    action = serializers.ChoiceField(
        choices=["fix", "reject", "comment"],
        required=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = self.context["user"]
        report = self.context["report"]
        if attrs.get("action") != "comment" and not user.is_authenticated:
            raise serializers.ValidationError(
                {
                    "action": [
                        "Vous devez être connecté pour changer le statut du signalement."
                    ]
                }
            )
        if report.is_closed():
            raise serializers.ValidationError(
                {"non_field_errors": ["Le signalement est déjà clos."]}
            )

        validated_data = {
            "text": attrs["message"],
            "email": attrs.get("email"),
            "status": self.get_status_from_action(attrs["action"]),
        }

        return validated_data

    def get_status_from_action(self, action: str) -> str:
        match action:
            case "fix":
                return "fixed"
            case "reject":
                return "rejected"
            case "comment":
                return "pending"
            case _:
                raise serializers.ValidationError({"action": ["Action invalide."]})


class ReplyToReportView(RNBLoggingMixin, APIView):
    throttle_scope = "create_report"

    def post(self, request: Request, report_id: int) -> Response:
        report = get_object_or_404(Report, id=report_id)

        input_serializer = ReplyToReportSerializer(
            data=request.data, context={"user": request.user, "report": report}
        )
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.validated_data
        text = data["text"]
        new_status = data["status"]
        email = data.get("email")
        authenticated_user = request.user if request.user.is_authenticated else None

        feve_found = report.add_message_and_update_status(
            text=text,
            created_by_user=authenticated_user,
            created_by_email=email,
            status=new_status,
        )

        serializer = ReportSerializer(report)

        # temporary hack to add feve_found
        data = dict(serializer.data)
        data["feve_found"] = feve_found

        return Response(data, status=status.HTTP_200_OK)
