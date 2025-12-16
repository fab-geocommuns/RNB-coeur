from django.contrib.auth.models import User
from django.contrib.gis.db import models
from .others import Department, City


class EventDetail(models.Model):
    id = models.AutoField(primary_key=True)
    event_id = models.UUIDField(null=False, db_index=True)
    event_type = models.CharField(max_length=255, null=False)
    event_origin = models.JSONField(null=False)
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=False, db_index=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=False, db_index=True
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, db_index=True)


class BuildingEventDetail(models.Model):
    id = models.AutoField(primary_key=True)
    event_id = models.UUIDField(null=False, db_index=True)
    rnb_id = models.CharField(max_length=12, null=False, db_index=True)
    changes = models.JSONField(null=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event_id", "rnb_id"],
                name="unique_event_id_rnb_id",
            )
        ]
