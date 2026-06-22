from typing import cast

from api_alpha.permissions import RNBReviewerPermission
from api_alpha.serializers.edition_annotation import (
    EditionAnnotationSerializer,
    EditionAnnotationWriteSerializer,
)
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from batid.models import BuildingWithHistory, EditionAnnotation
from django.contrib.auth.models import User
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class EditionAnnotationView(RNBLoggingMixin, APIView):
    """CRUD of the annotations of a single edition (event_id).

    This endpoint is for internal use for now and is deliberately not exposed in the
    public API documentation (no @rnb_doc).
    """

    permission_classes = [RNBReviewerPermission]

    def get(self, request: Request, event_id: str) -> Response:
        self._check_edition_exists(event_id)

        annotations = (
            EditionAnnotation.objects.filter(event_id=event_id)
            .select_related("reviewer__profile__organization")
            .order_by("created_at")
        )
        serializer = EditionAnnotationSerializer(annotations, many=True)
        return Response(serializer.data)

    def put(self, request: Request, event_id: str) -> Response:
        self._check_edition_exists(event_id)

        serializer = EditionAnnotationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # request.user is a real User here (RNBReviewerPermission requires it).
        reviewer = cast(User, request.user)
        annotation, created = EditionAnnotation.objects.update_or_create(
            event_id=event_id,
            reviewer=reviewer,
            defaults={"status": data["status"], "comment": data.get("comment")},
        )

        response_status = (
            http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
        )
        return Response(
            EditionAnnotationSerializer(annotation).data, status=response_status
        )

    def delete(self, request: Request, event_id: str) -> Response:
        self._check_edition_exists(event_id)

        reviewer = cast(User, request.user)
        deleted, _ = EditionAnnotation.objects.filter(
            event_id=event_id, reviewer=reviewer
        ).delete()
        if not deleted:
            raise NotFound(detail="No annotation to delete for the current reviewer")

        return Response(status=http_status.HTTP_204_NO_CONTENT)

    def _check_edition_exists(self, event_id: str) -> None:
        """Raise 404 if no building (active or historical) carries this event_id."""
        if not BuildingWithHistory.objects.filter(event_id=event_id).exists():
            raise NotFound(detail="Unknown event_id")
