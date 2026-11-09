import json
from collections import Counter
from typing import Any

from batid.models import City, Organization, UserProfile
from batid.utils.constants import ADS_GROUP_NAME
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


def _batch_errors(json_users: list[dict]) -> dict[str, list[str]]:
    """Return every problem of the batch by kind; empty dict when the batch is valid."""
    usernames = [json_user["username"] for json_user in json_users]
    insee_codes = {
        str(code)
        for json_user in json_users
        for code in json_user["organization_managed_cities"]
    }
    known_codes = set(
        City.objects.filter(code_insee__in=insee_codes).values_list(
            "code_insee", flat=True
        )
    )
    errors = {
        "existing_usernames": sorted(
            User.objects.filter(username__in=usernames).values_list(
                "username", flat=True
            )
        ),
        "duplicate_usernames": sorted(
            username for username, count in Counter(usernames).items() if count > 1
        ),
        "unknown_insee_codes": sorted(insee_codes - known_codes),
    }
    return {kind: values for kind, values in errors.items() if values}


class CreateAdsTokenView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            with transaction.atomic():
                json_users = json.loads(request.body)
                errors = _batch_errors(json_users)
                if errors:
                    return JsonResponse({"errors": errors}, status=400)

                users = []

                for json_user in json_users:
                    user = User.objects.create(
                        username=json_user["username"],
                        email=json_user.get("email", None),
                    )

                    group, created = Group.objects.get_or_create(name=ADS_GROUP_NAME)
                    user.groups.add(group)
                    user.set_unusable_password()
                    user.save()

                    organization, created = Organization.objects.get_or_create(
                        name=json_user["organization_name"],
                        defaults={
                            "managed_cities": json_user["organization_managed_cities"]
                        },
                    )

                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    profile.organization = organization
                    profile.save(update_fields=["organization"])

                    token, created = Token.objects.get_or_create(user=user)

                    users.append(
                        {
                            "username": user.username,
                            "organization_name": json_user["organization_name"],
                            "email": user.email,
                            "token": token.key,
                        }
                    )

                return JsonResponse({"created_users": users})
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)
