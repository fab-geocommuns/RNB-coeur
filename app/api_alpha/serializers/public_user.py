from django.contrib.auth.models import User
from rest_framework import serializers
from batid.services.user import get_display_name


class PublicUserSerializer(serializers.Serializer):
    def to_representation(self, instance: User | None) -> dict:
        return {
            "display_name": get_display_name(instance),
            "id": instance.pk if instance is not None else None,
            "username": instance.username if instance is not None else None,
        }
