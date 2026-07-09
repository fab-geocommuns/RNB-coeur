from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.db import models


class EventAnnotation(models.Model):
    """
    Annotation posted by a reviewer on a RNB event.

    An event (`event_id`) is any change on the `Building` model (edition, import,
    datafix...). Since the same `event_id` can appear on several buildings (merge/split),
    the annotation targets the `event_id`, not a specific building. `event_id` is
    therefore not a foreign key.
    """

    STATUS_CORRECT = "correct"
    STATUS_UNCERTAIN = "uncertain"
    STATUS_INCORRECT = "incorrect"
    STATUSES = [STATUS_CORRECT, STATUS_UNCERTAIN, STATUS_INCORRECT]

    id = models.AutoField(primary_key=True)
    event_id = models.UUIDField(null=False, db_index=True)
    reviewee = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        related_name="events_annotated_by_reviewer",
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=False,
        related_name="events_annotated_by_me",
    )
    status = models.CharField(
        choices=[(s, s) for s in STATUSES], max_length=10, null=False
    )
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event_id", "reviewer"],
                name="unique_annotation_per_reviewer_per_event",
            )
        ]
