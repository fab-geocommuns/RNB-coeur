from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.db.models import CheckConstraint, Q
from taggit.managers import TaggableManager

from .building import Building


class Report(models.Model):
    """
    Model for user reports about buildings
    """

    point: models.PointField = models.PointField(
        null=False, spatial_index=True, srid=4326
    )

    building: models.ForeignKey[Building | None, Building] = models.ForeignKey(
        Building,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reports",
    )

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("fixed", "Corrigé"),
        ("rejected", "Refusé"),
    ]
    status: models.CharField = models.CharField(
        choices=STATUS_CHOICES,
        max_length=10,
        null=False,
        default="pending",
        db_index=True,
    )

    created_by_user: models.ForeignKey[User | None, User] = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_reports",
    )

    created_by_email: models.EmailField = models.EmailField(null=True, blank=True)

    closed_by_user: models.ForeignKey[User | None, User] = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_reports",
    )

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    tags: TaggableManager = TaggableManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=("status",), name="report_status_idx"),
            models.Index(fields=("created_at",), name="report_created_at_idx"),
        ]
        constraints = [
            CheckConstraint(
                check=(
                    Q(created_by_user__isnull=False) & Q(created_by_email__isnull=True)
                )
                | (Q(created_by_user__isnull=True) & Q(created_by_email__isnull=False)),
                name="report_creator_exclusive",
            ),
        ]
