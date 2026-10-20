from typing import cast

from batid.models import EmailNotificationOptOut
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class PreferencesSerializer(serializers.Serializer):
    subscribed = serializers.BooleanField(required=True)


class NotificationPreferencesView(APIView):
    """Read / update the notification subscription of the logged-in user's email."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        # IsAuthenticated guarantees a real User here.
        user = cast(User, request.user)
        subscribed = not EmailNotificationOptOut.is_opted_out(user.email)
        return Response({"subscribed": subscribed})

    def put(self, request: Request) -> Response:
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = cast(User, request.user)
        subscribed = serializer.validated_data["subscribed"]
        if subscribed:
            EmailNotificationOptOut.opt_in(user.email)
        else:
            EmailNotificationOptOut.opt_out(user.email)

        return Response({"subscribed": subscribed})
