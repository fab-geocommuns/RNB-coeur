from rest_framework import serializers

from batid.models import Report
from batid.models import ReportMessage
from taggit.serializers import TagListSerializerField

from api_alpha.serializers.public_user import PublicUserSerializer


class DisplayedAuthorSerializer(serializers.Serializer):
    def to_representation(self, instance: Report | ReportMessage) -> dict:
        return PublicUserSerializer().to_representation(instance.created_by_user)


class ReportMessageSerializer(serializers.ModelSerializer):
    author = DisplayedAuthorSerializer(source="*")

    class Meta:
        model = ReportMessage
        fields = ["id", "text", "created_at", "author"]
        read_only_fields = fields


class ReportSerializer(serializers.ModelSerializer):
    tags = TagListSerializerField()
    author = DisplayedAuthorSerializer(source="*")
    messages = ReportMessageSerializer(source="messages.all", many=True)
    rnb_id = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "point",
            "rnb_id",
            "status",
            "created_at",
            "updated_at",
            "messages",
            "author",
            "tags",
        ]
        read_only_fields = fields

    def get_rnb_id(self, obj: Report) -> str | None:
        return obj.building.rnb_id if obj.building else None
