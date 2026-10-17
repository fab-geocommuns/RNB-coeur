from django.contrib.auth.models import User
from django.db import models

from .others import City, Department, Organization


class EditionActivity(models.Model):
    """
    One row per edition (a distinct event_id) made by a contributor
    (event_origin.source = "contribution").
    Rows are derived from the building history by batid.services.edition_activity
    and feed the public edition statistics (totals, rankings, newcomers).
    """

    event_id = models.UUIDField(unique=True, null=False)
    event_type = models.CharField(max_length=20, null=False, db_index=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False)
    # organization of the user when the edition was processed
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True)
    # null when the building point is outside any known city/department
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    # lower(sys_period) of the edition
    edited_at = models.DateTimeField(null=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "edited_at"], name="edition_activity_user_idx"
            ),
            models.Index(
                fields=["city", "edited_at"], name="edition_activity_city_idx"
            ),
            models.Index(
                fields=["department", "edited_at"], name="edition_activity_dpt_idx"
            ),
            models.Index(
                fields=["organization", "edited_at"], name="edition_activity_org_idx"
            ),
        ]
