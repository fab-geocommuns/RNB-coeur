import json
from collections import Counter
from typing import Any

from batid.models import City, Organization, UserProfile
from batid.utils.constants import ADS_GROUP_NAME
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class _AdsUserSerializer(serializers.Serializer):
    # Lengths mirror the User and Organization columns, so a valid entry cannot fail on insert.
    username = serializers.CharField(max_length=150)
    email = serializers.CharField(max_length=254, allow_blank=True)
    organization_name = serializers.CharField(max_length=100)
    # CharField also turns INSEE codes sent as JSON integers into strings.
    organization_managed_cities = serializers.ListField(child=serializers.CharField())


def _batch_errors(ads_users: list[dict]) -> dict[str, list[str]]:
    """Return every problem of the batch by kind; empty dict when the batch is valid."""
    usernames = [ads_user["username"] for ads_user in ads_users]
    insee_codes = {
        code
        for ads_user in ads_users
        for code in ads_user["organization_managed_cities"]
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


def _create_ads_user(ads_user: dict) -> dict:
    """Create the user, its ADS group membership, organization and token."""
    user = User.objects.create(
        username=ads_user["username"],
        email=ads_user["email"],
    )

    group, _ = Group.objects.get_or_create(name=ADS_GROUP_NAME)
    user.groups.add(group)
    user.set_unusable_password()
    user.save()

    organization, _ = Organization.objects.get_or_create(
        name=ads_user["organization_name"],
        defaults={"managed_cities": ads_user["organization_managed_cities"]},
    )

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.organization = organization
    profile.save(update_fields=["organization"])

    token, _ = Token.objects.get_or_create(user=user)

    return {
        "username": user.username,
        "organization_name": ads_user["organization_name"],
        "email": user.email,
        "token": token.key,
    }


class CreateAdsTokenView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            json_users = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)

        serializer = _AdsUserSerializer(data=json_users, many=True)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)
        ads_users = serializer.validated_data

        errors = _batch_errors(ads_users)
        if errors:
            return JsonResponse({"errors": errors}, status=400)

        try:
            with transaction.atomic():
                users = [_create_ads_user(ads_user) for ads_user in ads_users]
        except IntegrityError:
            # A concurrent request created one of these usernames after the check above:
            # the batch is rolled back, report it like any existing username.
            errors = _batch_errors(ads_users)
            if not errors:
                raise
            return JsonResponse({"errors": errors}, status=400)

        return JsonResponse({"created_users": users})
