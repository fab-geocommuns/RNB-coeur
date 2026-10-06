from rest_framework import serializers


class RollbackWriteSerializer(serializers.Serializer):
    """Write serializer for POST /editions/<event_id>/rollback/.

    A comment is required: it both justifies the rollback and ends up in the
    DataFix text created by `batid.services.rollback.rollback_event`. This mirrors
    the front-end flow, where the rollback button only appears once the reviewer has
    marked the edition as "incorrect" and is only enabled once they've written a
    comment.
    """

    comment = serializers.CharField(required=True, allow_blank=False)
