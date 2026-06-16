from batid.services.user import get_display_name
from django.contrib.auth.models import User
from rest_framework import serializers


class PublicUserSerializer(serializers.Serializer):
    def to_representation(self, instance: User | None) -> dict:
        organization = self._get_organization(instance)
        return {
            "display_name": get_display_name(instance),
            "id": instance.pk if instance is not None else None,
            "username": instance.username if instance is not None else None,
            "organization_name": organization.name if organization else None,
            "organization_short_name": (
                organization.short_name if organization else None
            ),
        }

    def _get_organization(self, instance: User | None):
        if instance is None or not hasattr(instance, "profile"):
            return None

        return instance.profile.organization
