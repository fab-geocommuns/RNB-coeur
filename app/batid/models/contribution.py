from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.db import models


class Contribution(models.Model):
    id = models.AutoField(primary_key=True)  # type: ignore[var-annotated]
    rnb_id = models.CharField(max_length=255, null=True)  # type: ignore[var-annotated]
    text = models.TextField(null=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True, null=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]
    review_user = models.ForeignKey(  # type: ignore[var-annotated]
        User, on_delete=models.PROTECT, null=True, blank=True
    )
