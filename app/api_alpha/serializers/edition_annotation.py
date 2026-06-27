from api_alpha.serializers.public_user import PublicUserSerializer
from batid.models import EditionAnnotation
from rest_framework import serializers


class EditionAnnotationSerializer(serializers.ModelSerializer):
    """Read serializer for an edition annotation."""

    reviewer = PublicUserSerializer()

    class Meta:
        model = EditionAnnotation
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


class EditionAnnotationWriteSerializer(serializers.Serializer):
    """Write serializer for upserting an edition annotation.

    No cross-validation between `comment` and `status`: a comment is accepted with any
    status, including `correct`.
    """

    status = serializers.ChoiceField(choices=EditionAnnotation.STATUSES)
    comment = serializers.CharField(required=False, allow_blank=True)
