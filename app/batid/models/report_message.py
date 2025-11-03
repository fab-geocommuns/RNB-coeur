from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.db.models import CheckConstraint
from django.db.models import Q

from .report import Report


class ReportMessage(models.Model):
    """
    Model for messages/comments on reports
    """

    report: models.ForeignKey[Report, Report] = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    created_by_user: models.ForeignKey[User | None, User] = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_report_messages",
    )

    created_by_email: models.EmailField = models.EmailField(null=True, blank=True)

    text: models.TextField = models.TextField(default=None, null=False, blank=False)

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]  # Order messages chronologically
        indexes = [
            models.Index(
                fields=("report", "created_at"),
                name="report_message_report_ts_idx",
            )
        ]
        constraints = [
            CheckConstraint(
                check=~(
                    Q(created_by_user__isnull=False) & Q(created_by_email__isnull=False)
                ),
                name="report_message_creator_not_both",
            ),
        ]
