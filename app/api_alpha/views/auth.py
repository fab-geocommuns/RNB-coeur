import binascii
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.http import QueryDict
from django.shortcuts import redirect
from django.utils import translation
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.permissions import RNBContributorPermission
from api_alpha.serializers import OrganizationSerializer
from api_alpha.serializers import UserSerializer
from api_alpha.utils.sandbox_client import SandboxClient
from api_alpha.utils.sandbox_client import SandboxClientError
from api_alpha.utils import RNBLoggingMixin
from batid.models import Organization
from batid.services.email import build_reset_password_email
from batid.services.user import get_user_id_b64
from batid.services.user import get_user_id_from_b64
from batid.tasks import create_sandbox_user


def create_user_in_sandbox(user_data: dict) -> None:
    user_data_without_password = {**user_data}
    user_data_without_password.pop("password")
    create_sandbox_user.delay(user_data_without_password)


class SandboxAuthenticationError(AuthenticationFailed):
    pass


def sandbox_only(func):
    def wrapper(self, request, *args, **kwargs):
        if settings.ENVIRONMENT != "sandbox":
            print("Sandbox only endpoint called in non-sandbox environment")
            raise NotFound()

        auth_header = request.headers.get("Authorization")
        expected_auth_header = f"Bearer {settings.SANDBOX_SECRET_TOKEN}"
        if not settings.SANDBOX_SECRET_TOKEN or auth_header != expected_auth_header:
            raise SandboxAuthenticationError()
        return func(self, request, *args, **kwargs)

    return wrapper


class RNBAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=response.data["token"])
        user = token.user
        return Response(
            {
                "id": user.id,
                "token": token.key,
                "username": user.username,
                "groups": [group.name for group in user.groups.all()],
            }
        )


class CreateUserView(APIView):
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        request_data = request.data
        if isinstance(request_data, QueryDict):
            request_data = request_data.dict()
        # we need French error message for the website
        with translation.override("fr"):
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
                        organization_serializer.data
                        if organization_serializer
                        else None
                    ),
                },
                status=status.HTTP_201_CREATED,
            )


class GetUserToken(APIView):
    @sandbox_only
    def get(self, request, user_email_b64):
        user_email = urlsafe_base64_decode(user_email_b64).decode()
        user = User.objects.get(email=user_email)
        try:
            token = Token.objects.get(user=user)
        except Token.DoesNotExist:
            token = None
        return Response({"token": token.key if token else None})


class GetCurrentUserTokens(APIView):
    permission_classes = [RNBContributorPermission]

    def get(self, request) -> Response:
        user = request.user
        token = Token.objects.get(
            user=user
        )  # Exists because it's used to authenticate the request

        sandbox_token = self._get_sandbox_token(user.email)

        return Response(
            {
                "production_token": token.key if token else None,
                "sandbox_token": sandbox_token,
            }
        )

    def _get_sandbox_token(self, user_email: str) -> str | None:
        if not settings.HAS_SANDBOX:
            return None

        try:
            return SandboxClient().get_user_token(user_email)
        except SandboxClientError:
            return None


class ActivateUser(APIView):
    def get(self, request, user_id_b64, token):
        try:
            uid = urlsafe_base64_decode(user_id_b64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        site_url = settings.FRONTEND_URL

        if user and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            return redirect(f"{site_url}/activation?status=success&email={user.email}")
        else:
            return redirect(f"{site_url}/activation?status=error")


class RequestPasswordReset(RNBLoggingMixin, APIView):
    def post(self, request):

        email = request.data.get("email")
        if email is None:
            return JsonResponse({"error": "L'adresse email est requise"}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # We do not want someone to know if an email is in the database or not:
            # even if the user does not exist, we still return a 204 status code
            return Response(None, status=204)

        # We found a user with the email, we continue

        # We generate the token. Note, Django does not need to store the "request new password" token in the database
        # (explanation: https://stackoverflow.com/questions/46234627/how-does-default-token-generator-store-tokens)
        token = default_token_generator.make_token(user)

        # We also need the user id in base 64
        user_id_b64 = get_user_id_b64(user)

        # Build the email to send
        email = build_reset_password_email(token, user_id_b64, email)

        # Send the email
        # Might do: use a queue to send the email instead of a synchronous call
        email.send()

        return Response(None, status=204)


class ChangePassword(RNBLoggingMixin, APIView):

    # About security:
    # This endpoint is used to change the password of a user. It is very sensitive. It should be hardened.
    # - In case of wrong user id/token couple, always return a 404 status code
    # - Throttle the endpoint to avoid brute force attacks
    # - Do not log the use of this endpoint, the risk would be to log the new password in the logs, which is a security risk.
    # - Validate the new password is strong enough (validated against the AUTH_PASSWORD_VALIDATORS validators set in settings.py)

    # about scoped throttles in DRF: https://www.django-rest-framework.org/api-guide/throttling/#scopedratethrottle
    throttle_scope = "change_password"

    def patch(self, request, user_id_b64, token):

        # #################
        # First, we verify the couple user_id/token is valid, otherwise we return a 404 status code

        try:
            # Convert Base 64 user id to string
            user_id = get_user_id_from_b64(user_id_b64)
        except binascii.Error:
            # We return a 404 status code if the user does not exist.
            # We do not provide information about the user or the token.
            return Response(None, status=404)

        # Retrieve the user
        try:

            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            # We return a 404 status code if the user does not exist.
            # We do not provide information about the user or the token.
            return Response(None, status=404)

        # We check if the token is valid
        if not default_token_generator.check_token(user, token):
            # We return a 404 status code if the token is not valid for this user.
            # We do not provide information about the user or the token.
            return Response(None, status=404)

        # #################
        # Second, we verify the new password is valid

        password = request.data.get("password")
        if password is None:
            return JsonResponse(
                {"error": ["Le nouveau mot de passe est requis"]}, status=400
            )

        confirm_password = request.data.get("confirm_password")
        if confirm_password is None:
            return JsonResponse(
                {"error": ["La confirmation du nouveau mot de passe est requise"]},
                status=400,
            )

        if password != confirm_password:
            return JsonResponse(
                {"error": ["Les deux mots de passe ne correspondent pas"]}, status=400
            )

        # Verify the password is strong enough (validated against the AUTH_PASSWORD_VALIDATORS validators set in settings.py)
        try:
            validate_password(password, user)
        except ValidationError as e:
            return JsonResponse({"error": e.messages}, status=400)

        # We change the password
        user.set_password(password)
        user.save()

        return Response(None, status=204)
