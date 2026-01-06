from datetime import datetime

from django.contrib.auth.models import User
from django.contrib.gis.db import models

from batid.models.others import Department


class Feve(models.Model):
    report = models.ForeignKey(
        "batid.Report",
        on_delete=models.PROTECT,
        null=False,
        db_index=True,
        related_name="feves",
    )
    found_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, db_index=True
    )
    found_at = models.DateTimeField(auto_now=False, null=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=False)

    def found(self, user):
        self.found_at = datetime.now()
        self.found_by = user
        self.save()
