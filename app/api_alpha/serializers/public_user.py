from django.contrib.auth.models import User
from rest_framework import serializers


class PublicUserSerializer(serializers.Serializer):
    def to_representation(self, instance: User | None) -> dict:
        return {
            "display_name": self._get_display_name(instance),
            "id": instance.pk if instance is not None else None,
            "username": instance.username if instance is not None else None,
        }

    def _get_display_name(self, instance: User | None) -> str:
        if instance is None:
            return "Anonyme"

        if not instance.first_name and not instance.last_name:
            return instance.username

        if instance.last_name is None or len(instance.last_name) == 0:
            return instance.first_name

        return f"{instance.first_name} {instance.last_name[0]}."
