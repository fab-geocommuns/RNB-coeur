from typing import cast

from api_alpha.exceptions import BadRequest
from api_alpha.permissions import RollbackPermission
from api_alpha.serializers.rollback import RollbackWriteSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from batid.exceptions import DatabaseInconsistency, EventUnknown, InvalidOperation
from batid.services.rollback import rollback_event
from django.contrib.auth.models import User
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class RollbackEventView(RNBLoggingMixin, APIView):
    """Revert a single event, identified by its event_id.

    This is the endpoint used by the "rollback" button in the annotation form of a
    building's history page: it is only offered there once the reviewer marks the
    edition as "incorrect" and writes a comment, which is why a comment is required
    here too (see RollbackWriteSerializer) and ends up in the DataFix text. Reserved
    to members of the "Rollback" group (see RollbackPermission). This endpoint is for
    internal use for now and is deliberately not exposed in the public API
    documentation (no @rnb_doc).
    """

    permission_classes = [RollbackPermission]

    def post(self, request: Request, event_id: str) -> Response:
        actor = cast(User, request.user)

        serializer = RollbackWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data["comment"]

        try:
            result = rollback_event(actor, event_id, comment=comment)
        except EventUnknown:
            raise NotFound(detail="Unknown event_id")
        except DatabaseInconsistency as e:
            raise BadRequest(detail=e.api_message())
        except InvalidOperation as e:
            raise BadRequest(detail=e.api_message_with_details())

        return Response(result)
