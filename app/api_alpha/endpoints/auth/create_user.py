import private_captcha
from api_alpha.exceptions import BadRequest
from api_alpha.serializers.serializers import UserSerializer
from api_alpha.utils.sandbox_client import has_sandbox_secret
from batid.services.sandbox import mirror_user_to_sandbox
from django.conf import settings
from django.db import transaction
from django.http import QueryDict
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


def is_captcha_valid(captcha_solution: str) -> bool:
    if (
        settings.PRIVATE_CAPTCHA_API_KEY is None
        or settings.PRIVATE_CAPTCHA_SITEKEY is None
    ):
        raise AssertionError(
            "PRIVATE_CAPTCHA_API_KEY or PRIVATE_CAPTCHA_SITEKEY is not set but ENABLE_CAPTCHA is True. Please check your settings."
        )
    client = private_captcha.Client(api_key=settings.PRIVATE_CAPTCHA_API_KEY)
    result = client.verify(
        solution=captcha_solution, sitekey=settings.PRIVATE_CAPTCHA_SITEKEY
    )
    return result.ok()


def validate_captcha(captcha_solution: str) -> None:
    if not settings.ENABLE_CAPTCHA:
        return

    if not is_captcha_valid(captcha_solution):
        raise BadRequest(detail="Captcha verification failed")


class CreateUserView(APIView):
    throttle_scope = "create_user"

    def get_throttles(self):
        # The production instance mirrors every new account here. That is trusted
        # server-to-server traffic, not the public signups the throttle protects
        # against, and it shares a single IP: leaving it throttled silently drops
        # accounts as soon as signups outpace the limit.
        if settings.ENVIRONMENT == "sandbox" and has_sandbox_secret(self.request):
            return []
        return super().get_throttles()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        request_data = request.data
        if isinstance(request_data, QueryDict):
            request_data = request_data.dict()
        validate_captcha(request_data.get("captcha_solution"))
        user_serializer = UserSerializer(data=request_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()

        # on_commit: the worker must never see the task before the user is committed.
        transaction.on_commit(lambda: mirror_user_to_sandbox(user))

        return Response(
            {"user": user_serializer.data},
            status=status.HTTP_201_CREATED,
        )
