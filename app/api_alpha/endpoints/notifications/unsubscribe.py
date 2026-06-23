from batid.models import EmailNotificationOptOut
from batid.services.email import read_unsubscribe_token
from django.core import signing
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class UnsubscribeSerializer(serializers.Serializer):
    token = serializers.CharField(required=True, allow_blank=False)


class UnsubscribeView(APIView):
    """Opt an email address out of notifications from a signed token (no auth)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = UnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            email = read_unsubscribe_token(serializer.validated_data["token"])
        except signing.BadSignature:
            return Response(
                {"token": ["Lien de désinscription invalide."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        EmailNotificationOptOut.opt_out(email)
        return Response({"email": email}, status=status.HTTP_200_OK)
