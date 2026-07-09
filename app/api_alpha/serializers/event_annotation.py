from api_alpha.serializers.public_user import PublicUserSerializer
from batid.models import EventAnnotation
from rest_framework import serializers


class EventAnnotationSerializer(serializers.ModelSerializer):
    """Read serializer for an event annotation."""

    reviewer = PublicUserSerializer()

    class Meta:
        model = EventAnnotation
        fields = [
            "id",
            "event_id",
            "status",
            "comment",
            "reviewer",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EventAnnotationWriteSerializer(serializers.Serializer):
    """Write serializer for upserting an event annotation.

    No cross-validation between `comment` and `status`: a comment is accepted with any
    status, including `correct`.
    """

    status = serializers.ChoiceField(choices=EventAnnotation.STATUSES)
    comment = serializers.CharField(required=False, allow_blank=True)
