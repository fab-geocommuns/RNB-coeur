from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.db.models import CheckConstraint, Q

from .report import Report


class ReportMessage(models.Model):
    """
    Model for messages/comments on reports
    """

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="messages",
    )  # type: ignore[var-annotated]

    created_by_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_report_messages",
    )  # type: ignore[var-annotated]

    # Email of the user who created the message (nullable)
    created_by_email = models.EmailField(null=True, blank=True)  # type: ignore[var-annotated]

    # Message text content
    text = models.TextField(null=False, blank=False, default=None)  # type: ignore[var-annotated]

    # Timestamp for the message
    timestamp = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]

    class Meta:
        ordering = ["timestamp"]  # Order messages chronologically
        indexes = [
            models.Index(
                fields=("report", "timestamp"),
                name="report_message_report_ts_idx",
            )
        ]
        constraints = [
            CheckConstraint(
                check=(
                    Q(created_by_user__isnull=False) & Q(created_by_email__isnull=True)
                )
                | (Q(created_by_user__isnull=True) & Q(created_by_email__isnull=False)),
                name="report_message_creator_exclusive",
            ),
        ]
