from rest_framework import serializers

from batid.models import Report
from batid.models import ReportMessage
from taggit.serializers import TagListSerializerField, TaggitSerializer

from api_alpha.serializers.public_user import PublicUserSerializer


class DisplayedAuthorSerializer(serializers.Serializer):
    def to_representation(self, instance: Report | ReportMessage) -> dict:
        return PublicUserSerializer(instance.created_by_user).to_representation()


class ReportMessageSerializer(serializers.ModelSerializer):
    author = DisplayedAuthorSerializer(source="*", read_only=True)

    class Meta:
        model = ReportMessage
        fields = ["id", "text", "created_at", "author"]


class ReportSerializer(serializers.ModelSerializer):
    tags = TagListSerializerField()
    author = DisplayedAuthorSerializer(source="*", read_only=True)
    messages = ReportMessageSerializer(source="messages.all", many=True, read_only=True)
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

    def get_rnb_id(self, obj: Report) -> str | None:
        return obj.building.rnb_id if obj.building else None
