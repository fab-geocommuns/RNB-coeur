import private_captcha
from django.conf import settings
from django.db import transaction
from django.http import QueryDict
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.exceptions import BadRequest
from api_alpha.serializers.serializers import OrganizationSerializer
from api_alpha.serializers.serializers import UserSerializer
from batid.models import Organization
from batid.tasks import create_sandbox_user
from batid.services.mattermost import notify_if_error


def create_user_in_sandbox(user_data: dict) -> None:
    user_data_without_password = {
        "first_name": user_data["first_name"],
        "last_name": user_data["last_name"],
        "email": user_data["email"],
        "username": user_data["username"],
        "organization_name": user_data.get("organization_name", None),
        "job_title": user_data.get("job_title", None),
    }
    create_sandbox_user.delay(user_data_without_password)


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

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        request_data = request.data
        if isinstance(request_data, QueryDict):
            request_data = request_data.dict()
        validate_captcha(request_data.get("captcha_solution"))
        user_serializer = UserSerializer(data=request_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()

        organization_serializer = None
        organization_name = request_data.get("organization_name")
        if organization_name:
            organization_serializer = OrganizationSerializer(
                data={"name": organization_name}
            )
            organization_serializer.is_valid(raise_exception=True)
            organization, created = Organization.objects.get_or_create(
                name=organization_name
            )
            organization.users.add(user)
            organization.save()

        if settings.HAS_SANDBOX:
            create_user_in_sandbox(request_data)

        return Response(
            {
                "user": user_serializer.data,
                "organization": (
                    organization_serializer.data if organization_serializer else None
                ),
            },
            status=status.HTTP_201_CREATED,
        )
