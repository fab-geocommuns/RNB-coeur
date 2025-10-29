import json
from django.http import JsonResponse
from django.http import HttpResponse
from django.db import transaction
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from batid.models import Organization
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.request import Request
from typing import Any
from rest_framework.authtoken.models import Token

from batid.utils.constants import ADS_GROUP_NAME


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


@extend_schema(exclude=True)
class CreateAdsTokenView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            with transaction.atomic():
                json_users = json.loads(request.body)
                users = []

                for json_user in json_users:
                    user, created = User.objects.get_or_create(
                        username=json_user["username"],
                        defaults={
                            "email": json_user.get("email", None),
                        },
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

                    organization.users.add(user)
                    organization.save()

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
