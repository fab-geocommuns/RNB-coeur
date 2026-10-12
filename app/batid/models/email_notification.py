from __future__ import annotations

from django.contrib.gis.db import models


class EmailNotificationOptOut(models.Model):
    """One row = this address no longer receives notification emails."""

    email: models.EmailField = models.EmailField(unique=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    @classmethod
    def is_opted_out(cls, email: str) -> bool:
        return cls.objects.filter(email=email.lower()).exists()

    @classmethod
    def opt_out(cls, email: str) -> None:
        cls.objects.get_or_create(email=email.lower())

    @classmethod
    def opt_in(cls, email: str) -> None:
        cls.objects.filter(email=email.lower()).delete()
