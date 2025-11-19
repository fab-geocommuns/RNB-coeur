from __future__ import annotations

from datetime import datetime

from django.contrib.auth.models import User
from django.contrib.gis.db import models


class Contribution(models.Model):
    id = models.AutoField(primary_key=True)  # type: ignore[var-annotated]
    rnb_id = models.CharField(max_length=255, null=True)  # type: ignore[var-annotated]
    text = models.TextField(null=True)  # type: ignore[var-annotated]
    email = models.EmailField(null=True, blank=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True, null=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]
    # is it a user report (a modification proposal or "signalement" in French) or a direct data modification?
    report = models.BooleanField(null=False, db_index=True, default=True)  # type: ignore[var-annotated]
    # useful for reports (signalements)
    status = models.CharField(  # type: ignore[var-annotated]
        choices=[("pending", "pending"), ("fixed", "fixed"), ("refused", "refused")],
        max_length=10,
        null=False,
        default="pending",
        db_index=True,
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)  # type: ignore[var-annotated]
    review_comment = models.TextField(null=True, blank=True)  # type: ignore[var-annotated]
    review_user = models.ForeignKey(  # type: ignore[var-annotated]
        User, on_delete=models.PROTECT, null=True, blank=True
    )
    # if an event on a Building (eg a deactivation) updates the status of a "signalement" (eg status set to refused).
    status_updated_by_event_id = models.UUIDField(null=True, db_index=True)  # type: ignore[var-annotated]

    def fix(self, user, review_comment=""):
        if self.status != "pending":
            raise ValueError("Contribution is not pending.")

        self.status = "fixed"
        self.status_changed_at = datetime.now()
        self.review_comment = review_comment
        self.review_user = user
        self.save()

    def refuse(self, user, review_comment="", status_updated_by_event_id=None):
        if self.status != "pending":
            raise ValueError("Contribution is not pending.")

        self.status = "refused"
        self.status_changed_at = datetime.now()
        self.review_comment = review_comment
        self.review_user = user
        self.status_updated_by_event_id = status_updated_by_event_id
        self.save()

    def reset_pending(self):
        """
        A signalement has been refused because its underlying building has been deactivated.
        The building is finally reactivated => we reset the signalement to a pending status.
        """
        self.status = "pending"
        self.status_changed_at = None
        self.review_comment = None
        self.review_user = None
        self.status_updated_by_event_id = None
        self.save()
