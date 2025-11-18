from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import CheckConstraint
from django.db.models import Q
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
        related_name="opened_reports",
    )

    created_by_email: models.EmailField = models.EmailField(null=True, blank=True)

    closed_by_user: models.ForeignKey[User | None, User] = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_reports",
    )

    closed_by_event_id: models.UUIDField = models.UUIDField(null=True, blank=True)

    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    tags: TaggableManager = TaggableManager()

    @staticmethod
    @transaction.atomic
    def create(
        point: Point,
        building: Building,
        text: str,
        email: str | None,
        user: User | None,
        tags: list[str],
    ) -> Report:
        report = Report.objects.create(
            point=point,
            building=building,
            created_by_user=user,
            created_by_email=email,
        )
        report.messages.create(text=text, created_by_user=user, created_by_email=email)  # type: ignore[attr-defined]
        report.save()
        report.tags.set(tags)
        return report

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                check=~(
                    Q(created_by_user__isnull=False) & Q(created_by_email__isnull=False)
                ),
                name="report_creator_not_both",
            ),
        ]
